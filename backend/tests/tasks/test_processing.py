"""The Celery task wrappers - the actual entry points a queue-mode worker runs.

``tests/routes/test_processing_queue.py`` covers the enqueue -> eager-run happy
path for ``task_process_image`` / ``task_process_stack`` through the HTTP
routes. This file covers the rest directly: the hourly cleanup sweep, the
folder-watch no-op, and a stacking task's failure path - none of which a route
test reaches, but all of which run for real, unattended, on the worker.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from sqlalchemy.orm import sessionmaker

from app.constants import STALE_JOB_SECONDS
from app.db.models import JobRecord, SessionRecord, StackRecord
from app.services.job import JobService
from app.services.storage import StorageService
from app.tasks.processing import (
    task_cleanup_sessions,
    task_process_stack,
    task_watch_stacking_folder,
)


@pytest.fixture
def task_db(db_engine, monkeypatch: pytest.MonkeyPatch) -> sessionmaker:
    """Point ``database.SessionLocal`` (what these tasks open directly, with no
    FastAPI dependency override in the loop) at the isolated test engine - the
    same swap ``conftest.client`` does, without needing a TestClient."""
    import app.db.database as database_module

    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(database_module, "SessionLocal", factory)
    return factory


def test_cleanup_sessions_removes_expired_state_and_fails_stale_jobs(
    task_db: sessionmaker, db_session
) -> None:
    storage = StorageService()
    past = datetime.now(UTC) - timedelta(hours=1)

    session_id = "sess-expired"
    storage.save_original(session_id, np.zeros((4, 4, 3), dtype=np.uint8))
    db_session.add(
        SessionRecord(
            session_id=session_id,
            image_path=str(storage.original_path(session_id)),
            original_filename="m31.jpg",
            expires_at=past,
        )
    )

    stack_id = "stack-expired"
    storage.stack_dir(stack_id, create=True)
    db_session.add(StackRecord(stack_id=stack_id, frame_count=4, expires_at=past))

    stale_job = JobService(db_session).create(None, job_id="job-stale")
    stale_job.created_at = datetime.now(UTC) - timedelta(seconds=STALE_JOB_SECONDS + 60)
    db_session.commit()

    removed = task_cleanup_sessions()

    assert removed == 3
    assert not storage.has_session(session_id)
    assert not storage.stack_dir(stack_id).exists()
    assert db_session.get(SessionRecord, session_id) is None
    assert db_session.get(StackRecord, stack_id) is None
    assert db_session.get(JobRecord, "job-stale").status == "failed"


def test_watch_stacking_folder_is_a_noop_when_unconfigured(task_db: sessionmaker) -> None:
    """The default state for every deployment that isn't using folder-watch -
    must be an inert no-op, never an error."""
    assert task_watch_stacking_folder() == "disabled"


def test_process_stack_marks_the_job_failed_and_reraises_on_error(
    task_db: sessionmaker, db_session
) -> None:
    """A stack that can't be found (deleted, or a bad id) must not vanish
    silently - the job record has to carry the failure for the UI/logs, and
    Celery has to see the exception."""
    job = JobService(db_session).create(None, job_id="job-missing-stack")

    with pytest.raises(Exception):  # noqa: B017 - whatever ResourceNotFoundError is today
        task_process_stack("no-such-stack", job.job_id)

    # The task committed through its own session (`task_db`'s factory), not
    # `db_session` - `create()`'s own `refresh()` left `job` un-expired in
    # `db_session`'s identity map, so a plain `.get()` would just return that
    # stale cached copy instead of re-querying.
    db_session.expire_all()
    failed = db_session.get(JobRecord, job.job_id)
    assert failed.status == "failed"
    assert failed.error
