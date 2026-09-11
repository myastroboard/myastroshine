"""Tests for app.db.database: init_db, get_db, and the column-backfill helpers.

test_migrations.py already covers _reconcile_schema_drift's repair/raise paths
against a real dropped column (``jobs.client_ip``, which has no default). This
file fills in the rest: init_db itself (both the fresh-database and
adopt-a-legacy-database branches), the get_db FastAPI dependency, and the
_column_backfill branches that client_ip's default-less column never exercises.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import Column, Engine, Integer, String, create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.db import database
from app.db.models import Base


@contextmanager
def _engine(url: str) -> Iterator[Engine]:
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    try:
        yield engine
    finally:
        engine.dispose()


def test_init_db_upgrades_a_fresh_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """A brand-new (nonexistent) SQLite file: data dir gets created and migrated
    to head, with no schema drift left behind."""
    from app.config import get_settings

    url = get_settings().resolved_database_url
    db_path = pathlib.Path(url.removeprefix("sqlite:///"))
    assert not db_path.parent.exists()

    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "_database_url", url)
    try:
        database.init_db()
        assert db_path.parent.exists()
        assert "alembic_version" in inspect(engine).get_table_names()
        assert database._missing_columns(engine) == {}
    finally:
        engine.dispose()


def test_init_db_adopts_a_legacy_database_at_head(monkeypatch: pytest.MonkeyPatch) -> None:
    """A database with tables but no alembic_version (predates migrations) gets
    stamped at head instead of replayed from migration zero."""
    from app.config import get_settings

    url = get_settings().resolved_database_url
    pathlib.Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    assert "alembic_version" not in inspect(engine).get_table_names()

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "_database_url", url)
    try:
        database.init_db()
        assert "alembic_version" in inspect(engine).get_table_names()
        assert database._missing_columns(engine) == {}
    finally:
        engine.dispose()


def test_get_db_yields_a_session_and_closes_it_afterwards(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(database, "SessionLocal", factory)

    closed: list[bool] = []
    original_close = Session.close

    def _tracking_close(self: Session) -> None:
        closed.append(True)
        original_close(self)

    monkeypatch.setattr(Session, "close", _tracking_close)

    gen = database.get_db()
    session = next(gen)
    try:
        assert isinstance(session, Session)
        assert closed == []
    finally:
        with pytest.raises(StopIteration):
            next(gen)
    assert closed == [True]
    engine.dispose()


def test_column_backfill_prefers_the_server_default_text() -> None:
    col = Column("status", String(20), server_default=text("'pending'"))
    assert database._column_backfill(col) == "'pending'"


def test_column_backfill_falls_back_to_the_python_default() -> None:
    col = Column("count", Integer, default=7)
    assert database._column_backfill(col) == 7


def test_column_backfill_skips_a_callable_default() -> None:
    col = Column("count", Integer, default=lambda: 7)
    assert database._column_backfill(col) is None


def test_column_backfill_returns_none_without_any_default() -> None:
    col = Column("count", Integer)
    assert database._column_backfill(col) is None


def test_reconcile_backfills_existing_rows_when_the_missing_column_has_a_default(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """client_ip (used by test_migrations.py) has no default, so it only exercises
    the ADD COLUMN / leave-NULL path. This drives the UPDATE-backfill branch."""
    with _engine(f"sqlite:///{tmp_path / 'backfill.db'}") as engine:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE widgets (id INTEGER PRIMARY KEY)"))
            conn.execute(text("INSERT INTO widgets (id) VALUES (1)"))

        fake_column = Column("status", String(20), default="pending")
        monkeypatch.setattr(database, "_missing_columns", lambda eng: {"widgets": [fake_column]})

        database._reconcile_schema_drift(engine, str(engine.url))

        with engine.connect() as conn:
            row = conn.execute(text("SELECT status FROM widgets WHERE id = 1")).fetchone()
        assert row is not None
        assert row[0] == "pending"
