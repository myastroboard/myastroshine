"""EnhancementService - orchestrates a single-image enhancement.

``run`` is the shared work: it drives the pipeline, updates the :class:`JobRecord`
at each stage, and best-effort publishes progress to Redis. Both the sync route
and the Celery task call it.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from sqlalchemy import select

from app.config import get_settings
from app.db.models import JobRecord, StackRecord
from app.exceptions import AppError, ImageProcessingError
from app.logging_config import get_logger
from app.models import ProcessingParameters, ProcessResponse
from app.services import progress
from app.services.engine_probe import get_engine_statuses
from app.services.external_denoise import ExternalDenoiseService, blend_denoise
from app.services.external_engine import ExternalEngineError, ModelEstimateCache
from app.services.external_starless import (
    ExternalStarlessService,
    StarlessSplitFn,
    blend_starless,
)
from app.services.image_processing import ImageProcessingService, StepCallback
from app.services.job import JobService
from app.services.session import SessionService
from app.services.star_detection import StarDetectionService
from app.services.starless import StarlessService
from app.services.storage import StorageService
from app.utils.app_settings import get_app_settings

logger = get_logger(__name__)


class _JobSuperseded(Exception):
    """A newer edit for this session landed - stop and drop this job's work."""


_ESTIMATE_SECONDS = {"queued": 8, "processing": 4}
#: An external-engine pass dominates the job's wall time (seconds to minutes vs.
#: milliseconds for a normal stage), so its live progress drives the bar across a
#: whole band. DeepSNR runs first (early stage), then StarNet2.
_DEEPSNR_PROGRESS_BAND = (12, 40)
_STARNET2_PROGRESS_BAND = (20, 80)


class EnhancementService:
    """Applies parameters to a session's image and persists the result."""

    def __init__(
        self,
        sessions: SessionService,
        storage: StorageService,
        processing: ImageProcessingService,
        jobs: JobService,
    ) -> None:
        self.sessions = sessions
        self.storage = storage
        self.processing = processing
        self.jobs = jobs

    def _emit(self, job_id: str) -> None:
        progress.publish(job_id, JobService.to_event(self.jobs.get(job_id)))

    def _backing_stack_id(self, session_id: str) -> str | None:
        """The stack whose composite backs this session, if the composite is on disk."""
        stack_id = self.sessions.db.scalar(
            select(StackRecord.stack_id).where(StackRecord.session_id == session_id)
        )
        if stack_id and self.storage.stack_composite_path(stack_id).exists():
            return str(stack_id)
        return None

    def dispatch(
        self, session_id: str, params: ProcessingParameters, client_ip: str | None = None
    ) -> ProcessResponse:
        """Create a job and either run it inline or hand it to the queue."""
        self.sessions.get_session(session_id)  # 404/410 before any work
        # A newer edit obsoletes any still-pending one for this session - retire
        # them so a burst of slider moves can't exhaust the concurrency budget.
        self.jobs.supersede_pending_for_session(session_id)
        self.jobs.assert_under_concurrency_limit(client_ip)
        job = self.jobs.create(session_id, client_ip=client_ip)

        if get_settings().processing_mode == "queue":
            # Lazy import: app.tasks.processing imports this module.
            from app.tasks.processing import task_process_image  # noqa: PLC0415

            task_process_image.delay(session_id, params.model_dump(), job.job_id)
        else:
            self.run(session_id, params, job.job_id)

        return self._response(self.jobs.get(job.job_id), session_id)

    @staticmethod
    def _response(job: JobRecord, session_id: str) -> ProcessResponse:
        return ProcessResponse(
            session_id=session_id,
            job_id=job.job_id,
            status=job.status,
            preview_url=f"/api/preview/{session_id}",
            estimated_time_seconds=_ESTIMATE_SECONDS.get(job.status, 0),
            ws_status_url=f"/ws/processing-status/{job.job_id}",
        )

    def _starless_split(
        self, session_id: str, params: ProcessingParameters, on_step: StepCallback
    ) -> StarlessSplitFn | None:
        """A StarNet2-backed split for the pipeline, or ``None`` for the classical path.

        Returns ``None`` (classical) unless star removal is on, the edit asked for
        ``"starnet2"``, and the operator has a working binary. The returned fn caches
        StarNet2's estimate per session and falls back to the classical split if a
        pass fails - so the pipeline can treat it as an ordinary split. ``on_step``
        is fed the live per-pass progress a StarNet2 run reports.
        """
        if params.star_removal <= 0 or params.star_removal_engine != "starnet2":
            return None
        if not get_engine_statuses()["starnet2"].found:
            logger.warning(
                "starnet2 engine requested but unavailable; using classical split",
                session_id=session_id,
            )
            return None

        settings = get_app_settings()
        low, high = _STARNET2_PROGRESS_BAND

        def report(fraction: float) -> None:
            on_step("star_removal", round(low + fraction * (high - low)))

        engine = ExternalStarlessService(
            settings.starnet2_path, settings.starnet2_stride, progress_cb=report
        )
        cache = ModelEstimateCache(self.storage, session_id, "starnet2")
        fallback = StarlessService(StarDetectionService())
        key = {"engine": "starnet2", "stride": settings.starnet2_stride}

        def split(
            image: np.ndarray, sensitivity: int, max_size: int, removal_amount: int
        ) -> tuple[np.ndarray, np.ndarray]:
            try:
                estimate = cache.get_or_compute(image, key, lambda: engine.run_model(image))
            except ExternalEngineError:
                logger.warning(
                    "starnet2 split failed; falling back to classical split",
                    session_id=session_id,
                    exc_info=True,
                )
                return fallback.split(image, sensitivity, max_size, removal_amount)
            return blend_starless(image, estimate, removal_amount)

        return split

    def _denoise_stage(
        self, session_id: str, params: ProcessingParameters, on_step: StepCallback
    ) -> Callable[[np.ndarray], np.ndarray] | None:
        """A DeepSNR denoise stage for the pipeline, or ``None`` for the classical filter.

        Same shape as :meth:`_starless_split`: returns ``None`` unless denoise is
        on, the edit asked for ``"deepsnr"``, and a working binary is configured.
        The returned fn (BGR ``uint8`` in and out) caches DeepSNR's estimate per
        session and falls back to the classical bilateral filter if a pass fails.
        """
        if params.denoise <= 0 or params.denoise_engine != "deepsnr":
            return None
        if not get_engine_statuses()["deepsnr"].found:
            logger.warning(
                "deepsnr engine requested but unavailable; using classical denoise",
                session_id=session_id,
            )
            return None

        settings = get_app_settings()
        low, high = _DEEPSNR_PROGRESS_BAND

        def report(fraction: float) -> None:
            on_step("denoise", round(low + fraction * (high - low)))

        engine = ExternalDenoiseService(
            settings.deepsnr_path, settings.deepsnr_stride, progress_cb=report
        )
        cache = ModelEstimateCache(self.storage, session_id, "deepsnr")
        key = {"engine": "deepsnr", "stride": settings.deepsnr_stride}

        def denoise(image: np.ndarray) -> np.ndarray:
            try:
                estimate = cache.get_or_compute(image, key, lambda: engine.run_model(image))
            except ExternalEngineError:
                logger.warning(
                    "deepsnr denoise failed; falling back to classical denoise",
                    session_id=session_id,
                    exc_info=True,
                )
                return self.processing.apply_denoise(image, params.denoise)
            return blend_denoise(image, estimate, params.denoise)

        return denoise

    def run(self, session_id: str, params: ProcessingParameters, job_id: str) -> None:
        """Enhance ``session_id`` with ``params``, tracking ``job_id``."""
        if self.jobs.get(job_id).status == "superseded":
            # A newer edit landed while this one waited in the queue.
            self._emit(job_id)
            logger.info("skipping superseded job", session_id=session_id, job_id=job_id)
            return
        self.jobs.update(job_id, status="processing", progress_percent=5, current_step="loading")
        self._emit(job_id)

        try:
            self.sessions.get_session(session_id)

            # Progress only moves forward within a job: the fixed per-stage
            # percentages would otherwise pull the bar back after an external
            # engine pass (below) has pushed it deep into a later range.
            progress_floor = 5

            def on_step(name: str, percent: int) -> None:
                nonlocal progress_floor
                # A newer edit for this session retires this job (dispatch ->
                # supersede_pending_for_session). Bail out here rather than
                # grinding a full pipeline - and a burst of DB writes - to a
                # result nobody will look at; the worker's other slot is then
                # free for the edit that replaced it.
                if self.jobs.get(job_id).status == "superseded":
                    raise _JobSuperseded
                progress_floor = max(progress_floor, percent)
                self.jobs.update(job_id, current_step=name, progress_percent=progress_floor)
                self._emit(job_id)

            starless_split = self._starless_split(session_id, params, on_step)
            denoise_stage = self._denoise_stage(session_id, params, on_step)
            stack_id = self._backing_stack_id(session_id)
            if stack_id is not None:
                # A stacked-composite session: run the pipeline on the 32-bit
                # linear composite (STF / background extraction / colour
                # calibration are the "Stack" step, params.stack) instead of the
                # pre-stretched uint8 upload.
                composite = self.storage.load_stack_composite(stack_id)
                result = self.processing.apply_parameters(
                    composite,
                    params,
                    on_step,
                    linear_composite=True,
                    starless_split=starless_split,
                    denoise_stage=denoise_stage,
                )
            else:
                original = self.storage.load_original(session_id)
                result = self.processing.apply_parameters(
                    original,
                    params,
                    on_step,
                    starless_split=starless_split,
                    denoise_stage=denoise_stage,
                )

            self.jobs.update(job_id, progress_percent=95, current_step="rendering")
            self._emit(job_id)
            self.storage.save_result(session_id, result)
            self.sessions.update_parameters(session_id, params.model_dump())
        except _JobSuperseded:
            self._emit(job_id)
            logger.info("dropped superseded job mid-run", session_id=session_id, job_id=job_id)
            return
        except AppError as exc:
            self.jobs.update(job_id, status="failed", error=exc.message)
            self._emit(job_id)
            raise
        except Exception as exc:
            logger.exception("processing failed", session_id=session_id, job_id=job_id)
            self.jobs.update(job_id, status="failed", error="Image processing failed")
            self._emit(job_id)
            raise ImageProcessingError("Image processing failed") from exc

        self.jobs.update(job_id, status="completed", progress_percent=100, current_step="done")
        self._emit(job_id)
        logger.info("image processed", session_id=session_id, job_id=job_id)
