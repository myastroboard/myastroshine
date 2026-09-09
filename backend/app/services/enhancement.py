"""EnhancementService - orchestrates a single-image enhancement.

``run`` is the shared work: it drives the pipeline, updates the :class:`JobRecord`
at each stage, and best-effort publishes progress to Redis. Both the sync route
and the Celery task call it.
"""

from __future__ import annotations

import numpy as np
from sqlalchemy import select

from app.config import get_settings
from app.db.models import JobRecord, StackRecord
from app.exceptions import AppError, ImageProcessingError
from app.logging_config import get_logger
from app.models import ProcessingParameters, ProcessResponse
from app.services import progress
from app.services.engine_probe import get_engine_statuses
from app.services.external_starless import (
    ExternalStarlessError,
    ExternalStarlessService,
    StarlessModelCache,
    StarlessSplitFn,
    blend_starless,
)
from app.services.image_processing import ImageProcessingService
from app.services.job import JobService
from app.services.session import SessionService
from app.services.star_detection import StarDetectionService
from app.services.starless import StarlessService
from app.services.storage import StorageService
from app.utils.app_settings import get_app_settings

logger = get_logger(__name__)

_ESTIMATE_SECONDS = {"queued": 8, "processing": 4}


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
        self, session_id: str, params: ProcessingParameters
    ) -> StarlessSplitFn | None:
        """A StarNet2-backed split for the pipeline, or ``None`` for the classical path.

        Returns ``None`` (classical) unless star removal is on, the edit asked for
        ``"starnet2"``, and the operator has a working binary. The returned fn caches
        StarNet2's estimate per session and falls back to the classical split if a
        pass fails - so the pipeline can treat it as an ordinary split.
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
        engine = ExternalStarlessService(settings.starnet2_path, settings.starnet2_stride)
        cache = StarlessModelCache(self.storage, session_id)
        fallback = StarlessService(StarDetectionService())
        key = {"engine": "starnet2", "stride": settings.starnet2_stride}

        def split(
            image: np.ndarray, sensitivity: int, max_size: int, removal_amount: int
        ) -> tuple[np.ndarray, np.ndarray]:
            try:
                estimate = cache.get_or_compute(image, key, lambda: engine.run_model(image))
            except ExternalStarlessError:
                logger.warning(
                    "starnet2 split failed; falling back to classical split",
                    session_id=session_id,
                    exc_info=True,
                )
                return fallback.split(image, sensitivity, max_size, removal_amount)
            return blend_starless(image, estimate, removal_amount)

        return split

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

            def on_step(name: str, percent: int) -> None:
                self.jobs.update(job_id, current_step=name, progress_percent=percent)
                self._emit(job_id)

            starless_split = self._starless_split(session_id, params)
            stack_id = self._backing_stack_id(session_id)
            if stack_id is not None:
                # A stacked-composite session: run the pipeline on the 32-bit
                # linear composite (STF / background extraction / colour
                # calibration are the "Stack" step, params.stack) instead of the
                # pre-stretched uint8 upload.
                composite = self.storage.load_stack_composite(stack_id)
                result = self.processing.apply_parameters(
                    composite, params, on_step, linear_composite=True, starless_split=starless_split
                )
            else:
                original = self.storage.load_original(session_id)
                result = self.processing.apply_parameters(
                    original, params, on_step, starless_split=starless_split
                )

            self.jobs.update(job_id, progress_percent=95, current_step="rendering")
            self._emit(job_id)
            self.storage.save_result(session_id, result)
            self.sessions.update_parameters(session_id, params.model_dump())
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
