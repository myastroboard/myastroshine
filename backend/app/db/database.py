"""SQLAlchemy engine, session factory, and FastAPI dependency."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import Column, create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from alembic.config import Config

from app.config import get_settings
from app.db.models import Base
from app.logging_config import get_logger

logger = get_logger(__name__)

_settings = get_settings()
_database_url = _settings.resolved_database_url
# ``timeout`` lets a caller wait out a brief write lock (a stack upload commits
# per frame; the beat runs cleanup writes) instead of erroring immediately. WAL
# would remove reader/writer contention entirely but its shared-memory file does
# not work over a Docker Desktop bind mount, so processing runs on the Celery
# worker instead (PROCESSING_MODE=queue) to keep the API off the hot path.
_connect_args = (
    {"check_same_thread": False, "timeout": 15} if _database_url.startswith("sqlite") else {}
)
_BACKEND_DIR = Path(__file__).resolve().parents[2]  # .../backend (or /app in the image)

engine = create_engine(_database_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _alembic_config() -> Config:
    """An Alembic ``Config`` that runs without the ini file (so ``env.py`` does
    not re-``fileConfig`` the app's logging) and with absolute paths."""
    from alembic.config import Config  # noqa: PLC0415 - only needed at startup

    cfg = Config()
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", _database_url)
    return cfg


def init_db() -> None:
    """Bring the database schema to Alembic ``head``.

    Called on API startup and on Celery worker init. A brand-new database is
    built entirely from the migrations; a legacy database from an earlier
    ``create_all`` (no ``alembic_version`` table) is filled in and stamped at
    ``head`` - one that predates a *column* change still needs a manual
    ``alembic upgrade``.
    """
    if _database_url.startswith("sqlite:///"):
        db_path = _database_url.removeprefix("sqlite:///")
        if db_path not in ("", ":memory:"):
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    from alembic import command  # noqa: PLC0415 - only needed at startup

    tables = set(inspect(engine).get_table_names())
    cfg = _alembic_config()
    if tables and "alembic_version" not in tables:
        Base.metadata.create_all(bind=engine)
        command.stamp(cfg, "head")
        logger.warning("adopted an unversioned database at head", url=_database_url)
    else:
        command.upgrade(cfg, "head")
        logger.info("database schema up to date", url=_database_url)

    _reconcile_schema_drift(engine, _database_url)


def _missing_columns(eng: Engine) -> dict[str, list[Column[Any]]]:
    """ORM columns that don't exist in ``eng``'s database, keyed by table.

    A migration edited *after* it ran (a common mistake during active
    development) leaves ``alembic_version`` at head while the schema is behind -
    ``alembic upgrade`` then has nothing to do and the gap only surfaces later as
    a cryptic ``no such column``.
    """
    inspector = inspect(eng)
    live = {t: {c["name"] for c in inspector.get_columns(t)} for t in inspector.get_table_names()}
    drift: dict[str, list[Column[Any]]] = {}
    for table in Base.metadata.sorted_tables:
        gap = [c for c in table.columns if c.name not in live.get(table.name, set())]
        if gap:
            drift[table.name] = gap
    return drift


def _reconcile_schema_drift(eng: Engine, url: str) -> None:
    """Detect (and, on SQLite, auto-repair) columns the migrations never added.

    SQLite is the single-file dev / hobby database - add the missing columns in
    place so ``docker compose up`` just works, and log loudly so the migration
    still gets fixed. Any other backend (Postgres = a real deployment) raises:
    migrations must be correct there, and ``tests/db/test_migrations.py`` keeps
    them that way.
    """
    drift = _missing_columns(eng)
    if not drift:
        return

    summary = ", ".join(f"{table}.{col.name}" for table, cols in drift.items() for col in cols)
    if not url.startswith("sqlite"):
        raise RuntimeError(
            f"database schema is behind the models (missing: {summary}); "
            "run the migrations or fix the one that was edited after it ran"
        )

    from sqlalchemy import text  # noqa: PLC0415 - only on the (rare) repair path

    # The table / column names come from Base.metadata (our own models), not user
    # input - the only bound value is the backfill literal.
    with eng.begin() as conn:
        for table, cols in drift.items():
            for col in cols:
                type_sql = col.type.compile(dialect=eng.dialect)
                conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{col.name}" {type_sql}'))
                fill = _column_backfill(col)
                if fill is None:
                    continue
                update = f'UPDATE "{table}" SET "{col.name}" = :v WHERE "{col.name}" IS NULL'  # noqa: S608
                conn.execute(text(update), {"v": fill})
    logger.error(
        "schema drift auto-repaired on SQLite - a migration is missing these columns: %s",
        summary,
    )


_UNSET = object()


def _column_backfill(column: Column[Any]) -> Any:
    """A literal to seed existing rows with, or ``None`` to leave them NULL."""
    server_arg = getattr(column.server_default, "arg", _UNSET)
    if server_arg is not _UNSET:
        return getattr(server_arg, "text", server_arg)  # SQL text, or a plain literal
    default = column.default
    if default is not None and not getattr(default, "is_callable", False):
        return getattr(default, "arg", None)
    return None


def get_db() -> Iterator[Session]:
    """Yield a database session, closing it afterwards (FastAPI dependency)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
