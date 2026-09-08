"""StackingService - the multi-frame stacking pipeline (linear rebuild).

initiate -> upload frames (each ingested to a linear ``LinearFrame``) -> process
-> the composite becomes a normal session so the single-image enhancement routes
work on it unchanged.

``process`` builds master calibration frames (Phase 2) then delegates the
score -> register -> normalise -> reject -> combine work to
:class:`app.services.integration.IntegrationService`. A post-stack colour/stretch
step is still to come - see ``initial_plan/12_STACKING_REBUILD.md``.
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import ABANDONED_STACK_SECONDS, STALE_STACK_WORK_SECONDS
from app.db.models import StackRecord
from app.exceptions import InvalidParameterError, ResourceNotFoundError
from app.logging_config import get_logger
from app.models import (
    InitiateStackRequest,
    ProcessStackRequest,
    StackParameters,
    StackStatistics,
)
from app.services import progress
from app.services.calibration import CALIBRATION_KINDS, CalibrationMasters, CalibrationService
from app.services.frame_quality import FrameQuality
from app.services.integration import IntegrationService, highpass_noise
from app.services.job import JobService
from app.services.post_stack import PostStackReport, apply_post_stack, render_stack_base
from app.services.session import SessionService
from app.services.storage import PreparedFrame, StorageService
from app.utils.app_settings import get_app_settings
from app.utils.linear_ingest import LinearFrame, ingest_frame

logger = get_logger(__name__)

_MIN_FRAMES = 2
_COLOR_NDIM = 3
_MAX_CALIBRATION_FRAMES = 256  # per kind - well above any real dark/flat/bias run


class StackingService:
    """Owns the lifecycle of a :class:`app.db.models.StackRecord`."""

    def __init__(self, db: Session, sessions: SessionService, storage: StorageService) -> None:
        self.db = db
        self.sessions = sessions
        self.storage = storage
        self._integration = IntegrationService(storage, workers=get_app_settings().stacking_workers)
        self._calibration = CalibrationService(storage)

    def _get(self, stack_id: str) -> StackRecord:
        record = self.db.get(StackRecord, stack_id)
        if record is None:
            raise ResourceNotFoundError(f"Stack {stack_id} not found")
        return record

    def initiate(self, config: InitiateStackRequest, *, source: str = "upload") -> StackRecord:
        app_settings = get_app_settings()
        if config.frame_count > app_settings.stacking_max_frames:
            raise InvalidParameterError(f"Too many frames (max {app_settings.stacking_max_frames})")
        record = StackRecord(
            stack_id=str(uuid.uuid4()),
            frame_count=config.frame_count,
            source=source,
            drizzle_factor=config.drizzle_factor,
            registration_transform=config.registration_transform,
            combination_method=config.combination_method,
            rejection_algo=config.rejection_algo,
            weighting=config.weighting,
            cosmetic_correction=config.cosmetic_correction,
            quality_filter=config.quality_filter,
            post_process=config.post_process,
            excluded_frames=[],
            included_frames=[],
            expires_at=datetime.now(UTC) + timedelta(hours=app_settings.stacking_retention_hours),
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        logger.info("stack initiated", stack_id=record.stack_id, frames=config.frame_count)
        return record

    def add_frame(self, stack_id: str, index: int, frame: LinearFrame) -> StackRecord:
        record = self._get(stack_id)
        if record.status not in ("waiting_for_frames", "ready"):
            raise InvalidParameterError(f"Stack {stack_id} is not accepting frames")
        max_frames = get_app_settings().stacking_max_frames
        if not 0 <= index < max_frames:
            raise InvalidParameterError(f"frame_index must be 0..{max_frames - 1}")

        already = self.storage.has_linear_frame(stack_id, index)
        self.storage.save_linear_frame(stack_id, index, frame)
        if not already:
            record.received_frames += 1
        record.frame_count = max(record.frame_count, index + 1)
        if record.received_frames >= _MIN_FRAMES:
            record.status = "ready"
        self.db.commit()
        self.db.refresh(record)
        return record

    def prepare_frame(self, data: bytes, filename: str | None) -> PreparedFrame:
        """Decode + pack + thumbnail one upload - pure CPU, run across a threadpool."""
        return self.storage.prepare_linear_frame(ingest_frame(data, filename))

    def add_frames(
        self, stack_id: str, start_index: int, prepared: list[PreparedFrame]
    ) -> StackRecord:
        """Write a batch of prepared frames to disk with a single DB commit."""
        record = self._get(stack_id)
        if record.status not in ("waiting_for_frames", "ready"):
            raise InvalidParameterError(f"Stack {stack_id} is not accepting frames")
        max_frames = get_app_settings().stacking_max_frames
        for offset, item in enumerate(prepared):
            index = start_index + offset
            if not 0 <= index < max_frames:
                raise InvalidParameterError(f"frame_index must be 0..{max_frames - 1}")
            if not self.storage.has_linear_frame(stack_id, index):
                record.received_frames += 1
            self.storage.write_linear_frame(stack_id, index, item)
            record.frame_count = max(record.frame_count, index + 1)
        if record.received_frames >= _MIN_FRAMES:
            record.status = "ready"
        self.db.commit()
        self.db.refresh(record)
        return record

    def set_frame_excluded(self, stack_id: str, index: int, excluded: bool) -> StackRecord:
        """Toggle a frame in/out of the stack.

        Also maintains the ``included_frames`` rescue list: unchecking a frame
        (``excluded=False``) protects it from the quality auto-reject on the next
        run; checking it drops that protection.
        """
        record = self._get(stack_id)
        if not self.storage.has_linear_frame(stack_id, index):
            raise ResourceNotFoundError(f"Frame {index} not uploaded for stack {stack_id}")
        dropped = set(record.excluded_frames or [])
        rescued = set(record.included_frames or [])
        if excluded:
            dropped.add(index)
            rescued.discard(index)
        else:
            dropped.discard(index)
            rescued.add(index)
        record.excluded_frames = sorted(dropped)
        record.included_frames = sorted(rescued)
        self.db.commit()
        self.db.refresh(record)
        return record

    # -- calibration frames (Phase 2) -----------------------------------

    def add_calibration_frames(
        self, stack_id: str, kind: str, frames: list[LinearFrame]
    ) -> StackRecord:
        """Append dark / flat / bias / dark_flat subs; masters are built at ``process``."""
        record = self._get(stack_id)
        if kind not in CALIBRATION_KINDS:
            raise InvalidParameterError(f"Unknown calibration frame kind {kind!r}")
        existing = self.storage.cal_frame_indices(stack_id, kind)
        if len(existing) + len(frames) > _MAX_CALIBRATION_FRAMES:
            raise InvalidParameterError(f"Too many {kind} frames (max {_MAX_CALIBRATION_FRAMES})")
        start = existing[-1] + 1 if existing else 0
        for offset, frame in enumerate(frames):
            self.storage.save_cal_frame(stack_id, kind, start + offset, frame)
        logger.info("calibration frames added", stack_id=stack_id, kind=kind, added=len(frames))
        return record

    def clear_calibration(self, stack_id: str, kind: str) -> StackRecord:
        record = self._get(stack_id)
        if kind not in CALIBRATION_KINDS:
            raise InvalidParameterError(f"Unknown calibration frame kind {kind!r}")
        self.storage.clear_cal_kind(stack_id, kind)
        return record

    def process(self, stack_id: str, job_id: str | None = None) -> StackRecord:
        record = self._get(stack_id)
        indices = self.storage.stack_frame_indices(stack_id)
        excluded = set(record.excluded_frames or [])
        kept = [i for i in indices if i not in excluded]
        if len(kept) < _MIN_FRAMES:
            raise InvalidParameterError("At least 2 frames are required to stack")

        record.status = "processing"
        self.db.commit()
        self._emit(job_id, stack_id, "calibration", 8)

        try:
            masters = self._build_masters(stack_id, kept, job_id)
            self._emit(job_id, stack_id, "integration", 20)
            composite, stats = self._integrate(
                record, stack_id, kept, len(excluded), masters, job_id
            )
        except Exception as exc:
            record.status = "failed"
            record.error = str(exc)
            self.db.commit()
            self._emit(job_id, stack_id, "failed", 100, status="failed", error=str(exc))
            logger.exception("stack processing failed", stack_id=stack_id)
            raise

        self.storage.save_stack_composite(stack_id, composite)
        session = self.sessions.create_session(
            image_path="", original_filename=f"stack_{stack_id[:8]}.png"
        )
        # Seed the editor's before/after images with the default "Stack" render
        # (background extraction + colour calibration + stretch); every later
        # /process rebuilds from composite.npy, so this only has to match the
        # StackParameters() defaults.
        display = np.clip(render_stack_base(composite, StackParameters()) * 255.0, 0, 255).astype(
            np.uint8
        )
        self.storage.save_original(session.session_id, display)
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
            frames=stats.frames_stacked,
        )
        return record

    def _build_masters(
        self, stack_id: str, kept: list[int], job_id: str | None
    ) -> CalibrationMasters | None:
        """Build (or load cached) master dark/flat/bias for the stack, if any exist."""
        if not self._calibration.has_frames(stack_id):
            return None
        sample = self.storage.load_linear_frame(stack_id, kept[0])
        masters = self._calibration.build_masters(
            stack_id,
            sample.data.shape,
            is_cfa=sample.is_cfa,
            on_progress=lambda pct: self._emit(job_id, stack_id, "calibration", 8 + int(pct * 0.1)),
        )
        logger.info("calibration masters ready", stack_id=stack_id)
        return masters

    def _integrate(
        self,
        record: StackRecord,
        stack_id: str,
        indices: list[int],
        excluded_count: int,
        masters: CalibrationMasters | None,
        job_id: str | None,
    ) -> tuple[np.ndarray, StackStatistics]:
        """Calibrate -> register -> normalise -> Winsorized-sigma weighted combine."""

        def on_progress(step: str, percent: int, detail: str | None = None) -> None:
            self._emit(job_id, stack_id, step, 15 + int(percent * 0.8), detail=detail)

        result = self._integration.integrate(
            stack_id,
            indices,
            transform=record.registration_transform,
            combination=record.combination_method,
            rejection=record.rejection_algo,
            weighting=record.weighting,
            quality_filter=record.quality_filter,
            protected=set(record.included_frames or []),
            calibration=masters,
            cosmetic=record.cosmetic_correction,
            drizzle=record.drizzle_factor,
            on_progress=on_progress,
        )

        composite = result.composite
        post_stack = None
        if record.post_process:
            self._emit(job_id, stack_id, "post-processing", 96)
            # Only the wedge crop is baked into composite.npy; background
            # extraction / colour calibration / stretch are non-destructive
            # editor steps (see post_stack.render_stack_base).
            composite, post_stack = apply_post_stack(result.composite, result.coverage)

        measured = None
        if result.reference_noise > 0:
            composite_noise = _background_noise(composite)
            if composite_noise > 0:
                measured = round(result.reference_noise / composite_noise, 2)

        calibrated = masters is not None and not masters.is_empty
        record.quality_report = {
            "reference_index": result.reference_index,
            "registration_rms_px": result.registration_rms,
            "registration_failures": result.registration_failures,
            "rejected_samples": result.rejected_samples,
            "aligned": result.aligned,
            "calibrated": calibrated,
            "quality_filter": record.quality_filter,
            "post_process": _post_stack_dict(post_stack),
            "frames": [_quality_dict(q) for q in result.frame_quality],
        }
        stats = StackStatistics(
            frames_stacked=result.frames_stacked,
            frames_excluded=excluded_count + result.registration_failures + result.quality_rejected,
            frames_auto_rejected=result.quality_rejected,
            combination_method=record.combination_method,
            registration_transform=record.registration_transform if result.aligned else "none",
            registration_rms_px=result.registration_rms if result.aligned else None,
            reference_frame=result.reference_index if result.aligned else None,
            snr_improvement=round(math.sqrt(result.effective_frames), 2),
            measured_noise_reduction=measured,
            calibrated=calibrated,
            post_processed=post_stack is not None and post_stack.cropped is not None,
            drizzle_factor=record.drizzle_factor,
        )
        return composite, stats

    def _emit(
        self,
        job_id: str | None,
        stack_id: str,
        step: str,
        percent: int,
        *,
        status: str = "processing",
        error: str | None = None,
        detail: str | None = None,
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
                "detail": detail,
                "error": error,
            },
        )

    def dispatch(
        self,
        stack_id: str,
        jobs: JobService,
        client_ip: str | None = None,
        overrides: ProcessStackRequest | None = None,
    ) -> tuple[StackRecord, str]:
        """Create a job and run the stack inline or on the queue.

        ``overrides`` re-stacks with a changed setting (no re-upload); each run
        produces a fresh composite session.
        """
        record = self._get(stack_id)  # 404 before any work
        if overrides is not None:
            changes = overrides.model_dump(exclude_none=True)
            for field, value in changes.items():
                setattr(record, field, value)
            if changes:
                self.db.commit()
        jobs.assert_under_concurrency_limit(client_ip)
        job = jobs.create(None, client_ip=client_ip)

        if get_settings().processing_mode == "queue":
            from app.tasks.processing import task_process_stack  # noqa: PLC0415

            task_process_stack.delay(stack_id, job.job_id)
        else:
            # Sync mode: drive the JobRecord to a terminal state ourselves, the
            # same way task_process_stack does on the queue - otherwise the row
            # sits at "queued" forever and counts against the per-IP concurrency
            # limit until the hourly stale-job sweep.
            jobs.update(job.job_id, status="processing", progress_percent=5)
            try:
                self.process(stack_id, job.job_id)
            except Exception as exc:
                jobs.update(job.job_id, status="failed", error=str(exc))
                raise
            jobs.update(job.job_id, status="completed", progress_percent=100)
        return self._get(stack_id), job.job_id

    def get_result(self, stack_id: str) -> StackRecord:
        return self._get(stack_id)

    def latest_watch_stack(self) -> StackRecord | None:
        """The most recent folder-watch stack that is still live, for the UI."""
        return self.db.scalars(
            select(StackRecord)
            .where(
                StackRecord.source == "watch",
                StackRecord.status.notin_(("expired",)),
                StackRecord.expires_at > datetime.now(UTC),
            )
            .order_by(StackRecord.created_at.desc())
        ).first()

    def cleanup_old_stacks(self) -> int:
        """Reclaim stack storage. Returns the number of stacks removed / repaired.

        The composite a stack produces becomes its own ``SessionRecord`` (expired
        by ``SessionService``); this only touches ``StackRecord`` rows and the
        frame / working files under ``DATA_DIR/images/stacks/``:

        1. expired rows and their directories;
        2. abandoned uploads (``waiting_for_frames`` / ``ready`` and older than
           ``ABANDONED_STACK_SECONDS``) - a night of frames is 8+ GB, so it does
           not wait for the full retention window;
        3. directories with no matching row (a half-deleted stack);
        4. an orphaned align-memmap (``accum/``) left by a dead ``processing``
           run - the stack is marked ``failed``.
        """
        now = datetime.now(UTC)
        removed = 0

        stale_upload_cutoff = now - timedelta(seconds=ABANDONED_STACK_SECONDS)
        doomed = self.db.scalars(
            select(StackRecord).where(
                (StackRecord.expires_at < now)
                | (
                    StackRecord.status.in_(("waiting_for_frames", "ready"))
                    & (StackRecord.created_at < stale_upload_cutoff)
                )
            )
        ).all()
        for record in doomed:
            self.storage.delete_stack(record.stack_id)
            self.db.delete(record)
            removed += 1
        self.db.commit()

        live_ids = set(self.db.scalars(select(StackRecord.stack_id)).all())
        accum_stale_before = now.timestamp() - STALE_STACK_WORK_SECONDS
        for stack_id in self.storage.stack_ids_on_disk():
            if stack_id not in live_ids:
                self.storage.delete_stack(stack_id)
                removed += 1
                continue
            mtime = self.storage.stack_accum_mtime(stack_id)
            if mtime is not None and mtime < accum_stale_before:
                self.storage.delete_stack_accum(stack_id)
                stuck = self.db.get(StackRecord, stack_id)
                if stuck is not None and stuck.status == "processing":
                    stuck.status, stuck.error = "failed", "processing was interrupted"
                removed += 1
        self.db.commit()

        if removed:
            logger.info("stacks cleaned", count=removed)
        return removed


def _background_noise(pixels: np.ndarray) -> float:
    """Robust high-pass noise of the composite (central crop, gradient removed)."""
    gray = pixels.mean(axis=2) if pixels.ndim == _COLOR_NDIM else pixels
    return highpass_noise(gray.astype(np.float32))


def _post_stack_dict(report: PostStackReport | None) -> dict[str, Any] | None:
    if report is None:
        return None
    return {"cropped": list(report.cropped) if report.cropped else None}


def _quality_dict(quality: FrameQuality) -> dict[str, Any]:
    """One scored frame as a JSON-safe dict for ``quality_report["frames"]``."""
    return {
        "index": quality.index,
        "star_count": quality.star_count,
        "fwhm": quality.fwhm,
        "roundness": quality.roundness,
        "background": quality.background,
        "snr": quality.snr,
        "score": quality.score,
        "weight": quality.weight,
        "accepted": quality.accepted,
        "reject_reason": quality.reject_reason,
    }
