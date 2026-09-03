"""SQLAlchemy engine, session factory, and FastAPI dependency."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import Base
from app.logging_config import get_logger

logger = get_logger(__name__)

_settings = get_settings()
_connect_args = {"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {}

engine = create_engine(_settings.database_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    """Create tables that do not exist yet.

    For real migrations use Alembic (``alembic upgrade head``); this is a
    convenience for local development and tests.
    """
    if _settings.database_url.startswith("sqlite:///"):
        db_path = _settings.database_url.removeprefix("sqlite:///")
        if db_path not in ("", ":memory:"):
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    logger.info("database initialized", url=_settings.database_url)


def get_db() -> Iterator[Session]:
    """Yield a database session, closing it afterwards (FastAPI dependency)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
