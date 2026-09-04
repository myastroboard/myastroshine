"""StackingService - the multi-frame stacking pipeline (v1.1).

initiate -> upload frames -> process (register -> normalise -> reject cosmic
rays -> combine). The composite becomes a normal session so the single-image
enhancement routes work on it unchanged.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import StackRecord
from app.exceptions import (
    InvalidParameterError,
    ResourceNotFoundError,
)
from app.logging_config import get_logger
from app.models import InitiateStackRequest, StackStatistics
from app.services import progress
from app.services.combination import CombinationService
from app.services.cosmic_ray import CosmicRayService
from app.services.job import JobService
from app.services.normalization import NormalizationService
from app.services.registration import RegistrationService
from app.services.session import SessionService
from app.services.storage import StorageService
from app.utils.app_settings import get_app_settings

logger = get_logger(__name__)

_MIN_FRAMES = 2


class StackingService:
    """Owns the lifecycle of a :class:`app.db.models.StackRecord`."""

    def __init__(self, db: Session, sessions: SessionService, storage: StorageService) -> None:
        self.db = db
        self.sessions = sessions
        self.storage = storage

    def _get(self, stack_id: str) -> StackRecord:
        record = self.db.get(StackRecord, stack_id)
        if record is None:
            raise ResourceNotFoundError(f"Stack {stack_id} not found")
        return record

    def initiate(self, config: InitiateStackRequest) -> StackRecord:
        app_settings = get_app_settings()
        if config.frame_count > app_settings.stacking_max_frames:
            raise InvalidParameterError(f"Too many frames (max {app_settings.stacking_max_frames})")
        record = StackRecord(
            stack_id=str(uuid.uuid4()),
            frame_count=config.frame_count,
            registration_method=config.registration_method,
            combination_method=config.combination_method,
            cosmic_ray_rejection=config.cosmic_ray_rejection,
            background_normalization=config.background_normalization,
            expires_at=datetime.now(UTC) + timedelta(hours=app_settings.session_expiry_hours),
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        logger.info("stack initiated", stack_id=record.stack_id, frames=config.frame_count)
        return record

    def add_frame(self, stack_id: str, index: int, image: np.ndarray) -> StackRecord:
        record = self._get(stack_id)
        if record.status not in ("waiting_for_frames", "ready"):
            raise InvalidParameterError(f"Stack {stack_id} is not accepting frames")
        if not 0 <= index < record.frame_count:
            raise InvalidParameterError(f"frame_index must be 0..{record.frame_count - 1}")

        already = self.storage.stack_frame_path(stack_id, index).exists()
        self.storage.save_stack_frame(stack_id, index, image)
        if not already:
            record.received_frames += 1
        if record.received_frames >= record.frame_count:
            record.status = "ready"
        self.db.commit()
        self.db.refresh(record)
        return record

    def process(self, stack_id: str, job_id: str | None = None) -> StackRecord:
        record = self._get(stack_id)
        frames = self.storage.load_stack_frames(stack_id)
        if len(frames) < _MIN_FRAMES:
            raise InvalidParameterError("At least 2 frames are required to stack")

        shapes = {f.shape for f in frames}
        if len(shapes) != 1:
            raise InvalidParameterError("All frames must have identical dimensions")

        record.status = "processing"
        self.db.commit()
        self._emit(job_id, stack_id, "registration", 10)

        try:
            composite, stats = self._run_pipeline(record, frames, job_id, stack_id)
        except Exception as exc:
            record.status = "failed"
            record.error = str(exc)
            self.db.commit()
            self._emit(job_id, stack_id, "failed", 100, status="failed", error=str(exc))
            logger.exception("stack processing failed", stack_id=stack_id)
            raise

        session = self.sessions.create_session(
            image_path="", original_filename=f"stack_{stack_id[:8]}.png"
        )
        self.storage.save_original(session.session_id, composite)
        session.image_path = str(self.storage.original_path(session.session_id))

        record.session_id = session.session_id
        record.status = "completed"
        record.result = stats.model_dump()
        self.db.commit()
        self.db.refresh(record)
        self._emit(job_id, stack_id, "done", 100, status="completed")
        logger.info(
            "stack completed",
            stack_id=stack_id,
            session_id=session.session_id,
            snr=stats.snr_improvement,
        )
        return record

    def _emit(
        self,
        job_id: str | None,
        stack_id: str,
        step: str,
        percent: int,
        *,
        status: str = "processing",
        error: str | None = None,
    ) -> None:
        if job_id is None:
            return
        progress.publish(
            job_id,
            {
                "job_id": job_id,
                "session_id": stack_id,
                "status": status,
                "progress_percent": percent,
                "current_step": step,
                "error": error,
            },
        )

    def _run_pipeline(
        self,
        record: StackRecord,
        frames: list[np.ndarray],
        job_id: str | None = None,
        stack_id: str = "",
    ) -> tuple[np.ndarray, StackStatistics]:
        registration = RegistrationService(record.registration_method).register(frames)
        aligned = registration.aligned

        if record.background_normalization:
            self._emit(job_id, stack_id, "background_normalization", 45)
            aligned = NormalizationService().normalize_backgrounds(aligned)

        reject_mask = None
        rays_removed = 0
        if record.cosmic_ray_rejection:
            self._emit(job_id, stack_id, "cosmic_ray_rejection", 65)
            reject_mask = CosmicRayService().build_mask(
                aligned, get_app_settings().stacking_cosmic_ray_threshold
            )
            rays_removed = int(reject_mask.sum())

        self._emit(job_id, stack_id, "combination", 85)
        combiner = CombinationService()
        composite = combiner.combine(aligned, record.combination_method, reject_mask)

        stats = StackStatistics(
            frames_stacked=len(aligned),
            frames_rejected=sum(1 for ok in registration.aligned_flags if not ok),
            combination_method=record.combination_method,
            cosmic_rays_removed=rays_removed,
            registration_success_rate=round(registration.success_rate * 100, 1),
            snr_improvement=round(combiner.estimate_snr_improvement(len(aligned)), 2),
        )
        return composite, stats

    def dispatch(self, stack_id: str, jobs: JobService) -> tuple[StackRecord, str]:
        """Create a job and run the stack inline or on the queue."""
        self._get(stack_id)  # 404 before any work
        job = jobs.create(None)

        if get_settings().processing_mode == "queue":
            from app.tasks.processing import task_process_stack  # noqa: PLC0415

            task_process_stack.delay(stack_id, job.job_id)
        else:
            self.process(stack_id, job.job_id)
        return self._get(stack_id), job.job_id

    def get_result(self, stack_id: str) -> StackRecord:
        return self._get(stack_id)
