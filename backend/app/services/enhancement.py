"""EnhancementService - orchestrates a single-image enhancement.

``run`` is the shared work: it drives the pipeline, updates the :class:`JobRecord`
at each stage, and best-effort publishes progress to Redis. Both the sync route
and the Celery task call it.
"""

from __future__ import annotations

from app.config import get_settings
from app.db.models import JobRecord
from app.exceptions import AppError, ImageProcessingError
from app.logging_config import get_logger
from app.models import ProcessingParameters, ProcessResponse
from app.services import progress
from app.services.image_processing import ImageProcessingService
from app.services.job import JobService
from app.services.session import SessionService
from app.services.storage import StorageService

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

    def dispatch(
        self, session_id: str, params: ProcessingParameters, client_ip: str | None = None
    ) -> ProcessResponse:
        """Create a job and either run it inline or hand it to the queue."""
        self.sessions.get_session(session_id)  # 404/410 before any work
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

    def run(self, session_id: str, params: ProcessingParameters, job_id: str) -> None:
        """Enhance ``session_id`` with ``params``, tracking ``job_id``."""
        self.jobs.update(job_id, status="processing", progress_percent=5, current_step="loading")
        self._emit(job_id)

        try:
            self.sessions.get_session(session_id)
            original = self.storage.load_original(session_id)

            def on_step(name: str, percent: int) -> None:
                self.jobs.update(job_id, current_step=name, progress_percent=percent)
                self._emit(job_id)

            result = self.processing.apply_parameters(original, params, on_step)

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
