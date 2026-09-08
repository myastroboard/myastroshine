"""Rate limiting wired onto the upload/process/stack routes (429 behaviour).

The service-level checks (window rollover, concurrency accounting) are unit
tested in ``tests/utils/test_rate_limit.py`` and ``tests/services/test_job.py``.
This file only exercises the route wiring: that the dependency actually runs
on these endpoints and that the client IP reaches ``JobRecord.client_ip``.
"""

from __future__ import annotations

import pytest

from app.services.job import JobService
from app.utils import app_settings


class _NotTestEnv:
    """Stands in for ``get_settings()`` with ``is_test=False`` (real enforcement).

    Patched only on the two modules that check it, rather than flipping
    ``APP_ENV`` globally - that would also disable Celery's eager test mode and
    the no-file-logging guard, which this test has no business touching.
    """

    is_test = False


@pytest.fixture
def _enforced(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.utils.rate_limit.get_settings", _NotTestEnv)
    monkeypatch.setattr("app.services.job.get_settings", _NotTestEnv)


def _upload(client, sample_jpeg: bytes):
    return client.post("/api/upload", files={"file": ("m31.jpg", sample_jpeg, "image/jpeg")})


def test_upload_429s_once_over_the_per_minute_limit(client, sample_jpeg: bytes, _enforced) -> None:
    app_settings.save_app_settings({"rate_limit_per_minute": 2})

    assert _upload(client, sample_jpeg).status_code == 200
    assert _upload(client, sample_jpeg).status_code == 200

    response = _upload(client, sample_jpeg)
    assert response.status_code == 429
    assert response.json()["error_code"] == "RATE_LIMITED"


def test_rate_limit_can_be_disabled(client, sample_jpeg: bytes, _enforced) -> None:
    app_settings.save_app_settings({"rate_limit_enabled": False, "rate_limit_per_minute": 1})

    for _ in range(3):
        assert _upload(client, sample_jpeg).status_code == 200


def test_process_records_the_client_ip(client, sample_jpeg: bytes, db_session) -> None:
    session_id = _upload(client, sample_jpeg).json()["session_id"]

    response = client.post(f"/api/process/{session_id}", json={"parameters": {"contrast": 1.5}})
    job_id = response.json()["job_id"]

    job = JobService(db_session).get(job_id)
    assert job.client_ip  # the connecting socket's address, whatever TestClient uses


def test_process_429s_once_the_concurrency_limit_is_already_reached(
    client, sample_jpeg: bytes, db_session, _enforced
) -> None:
    """Simulates an in-flight job by inserting one directly, since a sync-mode
    dispatch always finishes within the same request - two sequential HTTP
    calls can never observe each other as "concurrent" through the API alone.

    The in-flight job is for a *different* session: a new edit supersedes any
    still-pending job for its own session (so a slider drag can't 429 itself),
    but the per-IP budget still counts unrelated work."""
    other_session = _upload(client, sample_jpeg).json()["session_id"]
    session_id = _upload(client, sample_jpeg).json()["session_id"]
    app_settings.save_app_settings({"max_concurrent_jobs_per_ip": 1})

    jobs = JobService(db_session)
    in_flight = jobs.create(other_session, client_ip="testclient")
    assert in_flight.status == "queued"  # non-terminal - counts against the limit

    response = client.post(f"/api/process/{session_id}", json={"parameters": {"contrast": 1.5}})
    assert response.status_code == 429
    assert response.json()["error_code"] == "RATE_LIMITED"


def test_process_supersedes_its_own_pending_job_instead_of_429ing(
    client, sample_jpeg: bytes, db_session, _enforced
) -> None:
    """A burst of edits for one session must not exhaust the concurrency budget:
    the older pending job is retired, not counted."""
    session_id = _upload(client, sample_jpeg).json()["session_id"]
    app_settings.save_app_settings({"max_concurrent_jobs_per_ip": 1})

    jobs = JobService(db_session)
    stale = jobs.create(session_id, client_ip="testclient")

    response = client.post(f"/api/process/{session_id}", json={"parameters": {"contrast": 1.5}})
    assert response.status_code == 200

    db_session.refresh(stale)
    assert stale.status == "superseded"
