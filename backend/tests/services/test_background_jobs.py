"""The work that runs off the request (``app.services.background_jobs``): the
periodic cleanup and folder watch, a stack job's failure path, and the startup
sweep of jobs a previous process left unfinished."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.constants import STALE_JOB_SECONDS
from app.db.models import JobRecord, SessionRecord, StackRecord
from app.services.background_jobs import (
    cleanup_expired,
    fail_interrupted_jobs,
    run_stack_job,
    watch_stacking_folder,
)
from app.services.job import JobService
from app.services.storage import StorageService


def test_cleanup_removes_expired_state_and_fails_stale_jobs(job_db, db_session) -> None:
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

    removed = cleanup_expired()

    assert removed == 3
    assert not storage.has_session(session_id)
    assert not storage.stack_dir(stack_id).exists()
    db_session.expire_all()
    assert db_session.get(SessionRecord, session_id) is None
    assert db_session.get(StackRecord, stack_id) is None
    assert db_session.get(JobRecord, "job-stale").status == "failed"


def test_watch_stacking_folder_is_a_noop_when_unconfigured(job_db) -> None:
    """The default for every deployment not using folder watch: inert, never an error."""
    assert watch_stacking_folder() == "disabled"


def test_stack_job_marks_the_job_failed_and_reraises_on_error(job_db, db_session) -> None:
    """A stack that can't be found must not vanish silently: the job row carries
    the failure, and the runner sees the exception to log it."""
    job = JobService(db_session).create(None, job_id="job-missing-stack")

    with pytest.raises(Exception):  # noqa: B017 - whatever ResourceNotFoundError is today
        run_stack_job("no-such-stack", job.job_id)

    db_session.expire_all()
    failed = db_session.get(JobRecord, job.job_id)
    assert failed.status == "failed"
    assert failed.error


def test_fail_interrupted_jobs_closes_only_unfinished_jobs(job_db, db_session) -> None:
    """At startup, queued / processing jobs belong to a process that is gone."""
    jobs = JobService(db_session)
    queued = jobs.create(None, job_id="job-queued")
    running = jobs.create(None, job_id="job-running")
    jobs.update(running.job_id, status="processing")
    done = jobs.create(None, job_id="job-done")
    jobs.update(done.job_id, status="completed")

    assert fail_interrupted_jobs() == 2

    db_session.expire_all()
    assert db_session.get(JobRecord, queued.job_id).status == "failed"
    assert db_session.get(JobRecord, running.job_id).error == "interrupted by a restart"
    assert db_session.get(JobRecord, done.job_id).status == "completed"
