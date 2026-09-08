"""SQLAlchemy engine, session factory, and FastAPI dependency."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import create_engine, inspect
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


def get_db() -> Iterator[Session]:
    """Yield a database session, closing it afterwards (FastAPI dependency)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
