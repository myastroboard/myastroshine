"""The migrations must build the exact schema the ORM models describe.

This is the guard against the recurring "no such column" class of bug: a
migration edited after it ran, or a model change with no migration. Both leave a
fresh ``alembic upgrade head`` producing a schema that doesn't match
``Base.metadata`` - which this test catches in CI instead of hours later in a
beat task.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, text

from app.config import get_settings
from app.db import database
from app.db.models import Base

_BACKEND = pathlib.Path(__file__).resolve().parents[2]


@contextmanager
def _engine(url: str) -> Iterator[Engine]:
    engine = create_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def migrations_db_url() -> str:
    """The throwaway test DB URL, with its parent directory created (SQLite won't)."""
    url = get_settings().resolved_database_url
    assert url.startswith("sqlite:///")
    pathlib.Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return url


def _bare_cfg() -> Config:
    """Alembic config with no ini file - ``env.py`` picks the URL from settings
    (which the per-test fixture has pointed at a throwaway DATA_DIR)."""
    cfg = Config()
    cfg.set_main_option("script_location", str(_BACKEND / "migrations"))
    return cfg


def _schema(engine: Engine) -> dict[str, set[str]]:
    inspector = inspect(engine)
    schema = {
        table: {col["name"] for col in inspector.get_columns(table)}
        for table in inspector.get_table_names()
    }
    schema.pop("alembic_version", None)
    return schema


def test_migrations_from_scratch_match_the_models(migrations_db_url: str) -> None:
    command.upgrade(_bare_cfg(), "head")

    with _engine(migrations_db_url) as migrated, _engine("sqlite://") as fresh:
        Base.metadata.create_all(fresh)
        assert _schema(migrated) == _schema(fresh), "migrations and models have drifted apart"


def test_migrations_round_trip_to_base(migrations_db_url: str) -> None:
    cfg = _bare_cfg()
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    with _engine(migrations_db_url) as engine:
        assert set(_schema(engine)) == set(), "downgrade left tables behind"


def test_reconcile_repairs_a_column_a_stale_migration_missed(tmp_path: pathlib.Path) -> None:
    with _engine(f"sqlite:///{tmp_path / 'stale.db'}") as engine:
        Base.metadata.create_all(engine)
        # Simulate a DB stamped at head but missing a column the ORM expects.
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE jobs DROP COLUMN client_ip"))
        assert "jobs" in database._missing_columns(engine)

        database._reconcile_schema_drift(engine, str(engine.url))

        assert database._missing_columns(engine) == {}


def test_reconcile_raises_for_a_non_sqlite_backend(tmp_path: pathlib.Path) -> None:
    with _engine(f"sqlite:///{tmp_path / 'pg-lookalike.db'}") as engine:
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE jobs DROP COLUMN client_ip"))

        with pytest.raises(RuntimeError, match="schema is behind the models"):
            database._reconcile_schema_drift(engine, "postgresql://x/y")
