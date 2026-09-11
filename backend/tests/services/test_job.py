"""JobService: the durable job record."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.constants import STALE_JOB_SECONDS
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


def _age_job(db_session, job_id: str, seconds: int) -> None:
    job = JobService(db_session).get(job_id)
    job.created_at = datetime.now(UTC) - timedelta(seconds=seconds)
    db_session.commit()


def test_stale_non_terminal_jobs_stop_counting_toward_the_limit(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A job stuck 'queued' past STALE_JOB_SECONDS is treated as dead."""
    monkeypatch.setattr("app.services.job.get_settings", _NotTestEnv)
    app_settings.save_app_settings({"max_concurrent_jobs_per_ip": 1})
    service = JobService(db_session)

    stuck = service.create("sess-1", client_ip="1.2.3.4")
    _age_job(db_session, stuck.job_id, STALE_JOB_SECONDS + 60)

    assert service.count_active_for_ip("1.2.3.4") == 0
    service.assert_under_concurrency_limit("1.2.3.4")  # must not raise


def test_cleanup_stale_jobs_fails_only_the_old_non_terminal_ones(db_session) -> None:
    service = JobService(db_session)
    recent = service.create("sess-1", client_ip="1.2.3.4")
    old = service.create("sess-2", client_ip="1.2.3.4")
    _age_job(db_session, old.job_id, STALE_JOB_SECONDS + 60)
    done = service.create("sess-3", client_ip="1.2.3.4")
    service.update(done.job_id, status="completed")
    _age_job(db_session, done.job_id, STALE_JOB_SECONDS + 60)

    assert service.cleanup_stale_jobs() == 1
    assert service.get(old.job_id).status == "failed"
    assert service.get(recent.job_id).status == "queued"
    assert service.get(done.job_id).status == "completed"


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


def test_list_recent_hides_superseded_by_default(db_session) -> None:
    service = JobService(db_session)
    kept = service.create("sess-1")
    superseded = service.create("sess-1")
    service.update(superseded.job_id, status="superseded")

    rows, total = service.list_recent()

    assert total == 1
    assert [row.job_id for row in rows] == [kept.job_id]


def test_list_recent_can_filter_to_superseded_explicitly(db_session) -> None:
    service = JobService(db_session)
    service.create("sess-1")
    superseded = service.create("sess-1")
    service.update(superseded.job_id, status="superseded")

    rows, total = service.list_recent(status="superseded")

    assert total == 1
    assert [row.job_id for row in rows] == [superseded.job_id]


def test_list_recent_orders_newest_first_and_paginates(db_session) -> None:
    service = JobService(db_session)
    older = service.create("sess-1")
    _age_job(db_session, older.job_id, 120)
    newer = service.create("sess-2")

    rows, total = service.list_recent(limit=1)
    assert total == 2
    assert [row.job_id for row in rows] == [newer.job_id]

    rows, total = service.list_recent(limit=1, offset=1)
    assert total == 2
    assert [row.job_id for row in rows] == [older.job_id]


def test_prune_old_jobs_deletes_only_old_terminal_rows(db_session) -> None:
    service = JobService(db_session)
    recent_done = service.create("sess-1")
    service.update(recent_done.job_id, status="completed")

    old_done = service.create("sess-2")
    service.update(old_done.job_id, status="completed")
    _age_job(db_session, old_done.job_id, 8 * 3600)

    old_running = service.create("sess-3")
    _age_job(db_session, old_running.job_id, 8 * 3600)

    assert service.prune_old_jobs(retention_hours=1) == 1
    assert service.get_or_none(old_done.job_id) is None
    assert service.get(recent_done.job_id).status == "completed"  # too recent to prune
    assert service.get(old_running.job_id).status == "queued"  # not terminal - never pruned
