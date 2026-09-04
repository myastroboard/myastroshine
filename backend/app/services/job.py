"""JobService - the durable record of a processing job.

Every ``/process`` and ``/stack/*/process`` call creates a :class:`JobRecord`,
whether it runs inline (sync mode) or on the Celery queue. The WebSocket reads
the latest state here for late subscribers / catch-up.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import JobRecord
from app.exceptions import ResourceNotFoundError
from app.logging_config import get_logger
from app.types import JsonDict

logger = get_logger(__name__)

TERMINAL_STATUSES = ("completed", "failed")


class JobService:
    """CRUD for :class:`app.db.models.JobRecord`."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, session_id: str | None, *, job_id: str | None = None) -> JobRecord:
        record = JobRecord(
            job_id=job_id or f"job-{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            status="queued",
            progress_percent=0,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

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
