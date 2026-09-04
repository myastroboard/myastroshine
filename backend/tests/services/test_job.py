"""JobService: the durable job record."""

from __future__ import annotations

import pytest

from app.exceptions import ResourceNotFoundError
from app.services.job import JobService


def test_create_get_update(db_session) -> None:
    service = JobService(db_session)
    job = service.create("sess-1")
    assert job.status == "queued"
    assert job.progress_percent == 0

    service.update(job.job_id, status="processing", progress_percent=40, current_step="denoise")
    fresh = service.get(job.job_id)
    assert fresh.status == "processing"
    assert fresh.progress_percent == 40
    assert fresh.current_step == "denoise"


def test_create_allows_null_session(db_session) -> None:
    """Stack jobs have no session until the composite is made."""
    job = JobService(db_session).create(None)
    assert job.session_id is None


def test_get_missing_raises(db_session) -> None:
    with pytest.raises(ResourceNotFoundError):
        JobService(db_session).get("nope")
    assert JobService(db_session).get_or_none("nope") is None


def test_to_event_shape(db_session) -> None:
    job = JobService(db_session).create("sess-1")
    event = JobService.to_event(job)
    assert set(event) == {
        "job_id",
        "session_id",
        "status",
        "progress_percent",
        "current_step",
        "error",
        "timestamp",
    }
