"""JobService - the durable record of a processing job.

Every ``/process`` and ``/stack/*/process`` call creates a :class:`JobRecord`,
whether it runs inline (sync mode) or on the Celery queue. The WebSocket reads
the latest state here for late subscribers / catch-up.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import JobRecord
from app.exceptions import RateLimitedError, ResourceNotFoundError
from app.logging_config import get_logger
from app.types import JsonDict
from app.utils.app_settings import get_app_settings

logger = get_logger(__name__)

TERMINAL_STATUSES = ("completed", "failed")


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
        """Non-terminal jobs currently attributed to ``client_ip``."""
        return (
            self.db.query(func.count(JobRecord.job_id))
            .filter(JobRecord.client_ip == client_ip, JobRecord.status.notin_(TERMINAL_STATUSES))
            .scalar()
            or 0
        )

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
