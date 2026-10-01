"""Tests for app.main: the create_app factory and the lifespan startup/shutdown
hook. The `client` fixture in conftest.py deliberately never starts the real
lifespan (it wires dependency_overrides instead) - these exercise it directly.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.main as main_module
from app.db import database as database_module


@pytest.fixture
def _fresh_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the module-level engine/SessionLocal at this test's isolated DB.

    The autouse `_isolated_env` fixture already points settings at a per-test
    DATA_DIR; the module-level engine/_database_url/SessionLocal in
    app.db.database were bound once at first import and need repointing here,
    same as the `client` fixture does for routes.
    """
    from app.config import get_settings

    url = get_settings().resolved_database_url
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(database_module, "engine", engine)
    monkeypatch.setattr(database_module, "_database_url", url)
    monkeypatch.setattr(database_module, "SessionLocal", factory)
    try:
        yield
    finally:
        engine.dispose()


async def test_lifespan_runs_startup_and_shutdown_without_error(_fresh_db: None) -> None:
    dummy_app = FastAPI()
    async with main_module.lifespan(dummy_app):
        pass  # startup completed; shutdown logging runs on context exit


async def test_lifespan_fails_leftover_jobs_runs_the_scheduler_and_stops_the_runner(
    _fresh_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Startup closes jobs a previous process left unfinished and starts the
    periodic tasks; shutdown stops them and the job runner."""
    from app.db.database import init_db
    from app.db.models import JobRecord
    from app.services import job_runner
    from app.services.job import JobService

    init_db()
    with database_module.SessionLocal() as db:
        JobService(db).create(None, job_id="job-left-over")
    events: list[str] = []
    monkeypatch.setattr(main_module.Scheduler, "start", lambda self: events.append("start"))

    async def _stop(self: object) -> None:
        events.append("stop")

    monkeypatch.setattr(main_module.Scheduler, "stop", _stop)

    async with main_module.lifespan(FastAPI()):
        runner = job_runner.get_job_runner()
        with database_module.SessionLocal() as db:
            assert db.get(JobRecord, "job-left-over").status == "failed"

    assert events == ["start", "stop"]
    assert runner.stopping.is_set()
    assert job_runner.get_job_runner() is not runner  # a fresh one after shutdown


async def test_lifespan_consumes_an_admin_reset_marker(_fresh_db: None) -> None:
    """A ``reset-admin`` file in the data directory clears the admin password at
    startup - the way back in when the CLI is out of reach (Home Assistant)."""
    from app.config import get_settings
    from app.db.database import init_db
    from app.services.admin_auth import AdminAuthService

    init_db()
    with database_module.SessionLocal() as db:
        AdminAuthService(db).setup("a long enough password", None, None)
    marker = get_settings().data_dir / "reset-admin"
    marker.touch()

    async with main_module.lifespan(FastAPI()):
        with database_module.SessionLocal() as db:
            assert not AdminAuthService(db).is_configured()
    assert not marker.exists()


def test_create_app_mounts_the_frontend_when_the_static_dir_exists(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(main_module, "STATIC_DIR", static_dir)

    app = main_module.create_app()

    assert any(getattr(route, "name", None) == "frontend" for route in app.routes)


def test_create_app_skips_the_frontend_mount_when_the_static_dir_is_absent(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main_module, "STATIC_DIR", tmp_path / "does-not-exist")

    app = main_module.create_app()

    assert not any(getattr(route, "name", None) == "frontend" for route in app.routes)
