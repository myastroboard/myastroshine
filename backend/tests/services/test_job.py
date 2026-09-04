"""JobService: the durable job record."""

from __future__ import annotations

import pytest

from app.exceptions import RateLimitedError, ResourceNotFoundError
from app.services.job import JobService
from app.utils import app_settings


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


def test_create_stores_client_ip(db_session) -> None:
    job = JobService(db_session).create("sess-1", client_ip="203.0.113.5")
    assert job.client_ip == "203.0.113.5"


def test_count_active_for_ip_excludes_terminal_jobs(db_session) -> None:
    service = JobService(db_session)
    active = service.create("sess-1", client_ip="1.2.3.4")
    done = service.create("sess-2", client_ip="1.2.3.4")
    service.update(done.job_id, status="completed")
    service.create("sess-3", client_ip="9.9.9.9")  # a different IP

    assert service.count_active_for_ip("1.2.3.4") == 1
    assert service.count_active_for_ip("9.9.9.9") == 1
    assert active.status == "queued"


class _NotTestEnv:
    """Stands in for ``get_settings()`` with ``is_test=False`` (real enforcement)."""

    is_test = False


def test_concurrency_limit_raises_once_exceeded(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.job.get_settings", _NotTestEnv)
    app_settings.save_app_settings({"max_concurrent_jobs_per_ip": 2})

    service = JobService(db_session)
    service.create("sess-1", client_ip="1.2.3.4")
    service.create("sess-2", client_ip="1.2.3.4")

    with pytest.raises(RateLimitedError):
        service.assert_under_concurrency_limit("1.2.3.4")

    service.assert_under_concurrency_limit("9.9.9.9")  # a different IP is unaffected


def test_concurrency_limit_ignores_finished_jobs(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.job.get_settings", _NotTestEnv)
    app_settings.save_app_settings({"max_concurrent_jobs_per_ip": 1})

    service = JobService(db_session)
    job = service.create("sess-1", client_ip="1.2.3.4")
    service.update(job.job_id, status="completed")

    service.assert_under_concurrency_limit("1.2.3.4")  # must not raise


def test_concurrency_limit_skips_unattributed_requests(db_session) -> None:
    JobService(db_session).assert_under_concurrency_limit(None)  # must not raise


def test_concurrency_limit_is_a_noop_under_app_env_test(db_session) -> None:
    """The default test env bypasses enforcement (see test_rate_limit.py)."""
    app_settings.save_app_settings({"max_concurrent_jobs_per_ip": 1})
    service = JobService(db_session)
    service.create("sess-1", client_ip="1.2.3.4")
    service.create("sess-2", client_ip="1.2.3.4")

    service.assert_under_concurrency_limit("1.2.3.4")  # would raise if enforced


def test_concurrency_limit_respects_the_disabled_flag(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.job.get_settings", _NotTestEnv)
    app_settings.save_app_settings({"rate_limit_enabled": False, "max_concurrent_jobs_per_ip": 1})

    service = JobService(db_session)
    service.create("sess-1", client_ip="1.2.3.4")
    service.create("sess-2", client_ip="1.2.3.4")

    service.assert_under_concurrency_limit("1.2.3.4")  # must not raise
