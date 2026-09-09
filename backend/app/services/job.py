"""JobService - the durable record of a processing job.

Every ``/process`` and ``/stack/*/process`` call creates a :class:`JobRecord`,
whether it runs inline (sync mode) or on the Celery queue. The WebSocket reads
the latest state here for late subscribers / catch-up.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import STALE_JOB_SECONDS
from app.db.models import JobRecord
from app.exceptions import RateLimitedError, ResourceNotFoundError
from app.logging_config import get_logger
from app.services import progress
from app.types import JsonDict
from app.utils.app_settings import get_app_settings

logger = get_logger(__name__)

TERMINAL_STATUSES = ("completed", "failed", "superseded")


class JobService:
    """CRUD for :class:`app.db.models.JobRecord`."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self, session_id: str | None, *, job_id: str | None = None, client_ip: str | None = None
    ) -> JobRecord:
        record = JobRecord(
            job_id=job_id or f"job-{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            status="queued",
            progress_percent=0,
            client_ip=client_ip,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def count_active_for_ip(self, client_ip: str) -> int:
        """Non-terminal jobs from ``client_ip`` that are still plausibly running.

        A job left non-terminal for longer than ``STALE_JOB_SECONDS`` (a worker
        died mid-run, or the queue never picked it up) is treated as dead and
        does not count - otherwise a handful of stuck rows would permanently
        exhaust the per-IP concurrency budget. ``cleanup_stale_jobs`` sweeps
        those rows for good on the hourly schedule.
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=STALE_JOB_SECONDS)
        return (
            self.db.query(func.count(JobRecord.job_id))
            .filter(
                JobRecord.client_ip == client_ip,
                JobRecord.status.notin_(TERMINAL_STATUSES),
                JobRecord.created_at > cutoff,
            )
            .scalar()
            or 0
        )

    def supersede_pending_for_session(self, session_id: str) -> int:
        """Retire this session's not-yet-finished jobs - a newer edit is on the way.

        The editor re-processes on every settled slider move; without this, a
        burst of edits leaves a queue of stale jobs that each still count against
        the per-IP concurrency budget (429) and each still run to completion on
        the worker for a result nobody will look at. ``EnhancementService.run``
        skips a job it finds already superseded.
        """
        pending = self.db.scalars(
            select(JobRecord).where(
                JobRecord.session_id == session_id,
                JobRecord.status.notin_(TERMINAL_STATUSES),
            )
        ).all()
        for record in pending:
            record.status = "superseded"
        self.db.commit()
        # Tell any open progress socket now, so it closes instead of waiting for
        # the worker to reach this job and emit the terminal event itself.
        for record in pending:
            progress.publish(record.job_id, self.to_event(record))
        return len(pending)

    def cleanup_stale_jobs(self) -> int:
        """Mark long-abandoned non-terminal jobs failed. Returns the count."""
        cutoff = datetime.now(UTC) - timedelta(seconds=STALE_JOB_SECONDS)
        stale = self.db.scalars(
            select(JobRecord).where(
                JobRecord.status.notin_(TERMINAL_STATUSES),
                JobRecord.created_at <= cutoff,
            )
        ).all()
        for record in stale:
            record.status = "failed"
            record.error = "abandoned (no result within the expected time)"
        self.db.commit()
        if stale:
            logger.info("stale jobs cleaned", count=len(stale))
        return len(stale)

    def assert_under_concurrency_limit(self, client_ip: str | None) -> None:
        """Raise :class:`RateLimitedError` once ``client_ip`` has too many active jobs.

        The "5 concurrent processing jobs per IP" API-spec limit. Queries the
        shared ``jobs`` table rather than counting in-process, so it is correct
        regardless of ``PROCESSING_MODE`` (sync or Celery queue) - unlike a
        request-rate limiter, a per-process counter can't see jobs finishing on
        a different worker process. A no-op under ``APP_ENV=test`` and when the
        caller couldn't attribute a client IP.
        """
        if get_settings().is_test or client_ip is None:
            return
        settings = get_app_settings()
        if not settings.rate_limit_enabled:
            return
        if self.count_active_for_ip(client_ip) >= settings.max_concurrent_jobs_per_ip:
            raise RateLimitedError(
                "Too many concurrent processing jobs, please wait for one to finish",
                details={"max_concurrent_jobs": settings.max_concurrent_jobs_per_ip},
            )

    def get(self, job_id: str) -> JobRecord:
        record = self.db.get(JobRecord, job_id)
        if record is None:
            raise ResourceNotFoundError(f"Job {job_id} not found")
        return record

    def get_or_none(self, job_id: str) -> JobRecord | None:
        return self.db.get(JobRecord, job_id)

    def update(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress_percent: int | None = None,
        current_step: str | None = None,
        error: str | None = None,
    ) -> JobRecord:
        record = self.get(job_id)
        if status is not None:
            record.status = status
        if progress_percent is not None:
            record.progress_percent = progress_percent
        if current_step is not None:
            record.current_step = current_step
        if error is not None:
            record.error = error
        self.db.commit()
        self.db.refresh(record)
        return record

    @staticmethod
    def to_event(record: JobRecord) -> JsonDict:
        """The JSON message shape sent over the WebSocket."""
        return {
            "job_id": record.job_id,
            "session_id": record.session_id,
            "status": record.status,
            "progress_percent": record.progress_percent,
            "current_step": record.current_step,
            "error": record.error,
            "timestamp": datetime.now(UTC).isoformat(),
        }
