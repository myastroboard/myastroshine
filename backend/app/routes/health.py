"""Health check endpoint."""

from __future__ import annotations

from datetime import UTC, datetime

import redis
from fastapi import APIRouter
from sqlalchemy import text

from app import __version__
from app.config import get_settings
from app.dependencies import DbSession
from app.types import JsonDict
from app.utils.disk_usage import volume_usage

router = APIRouter(tags=["system"])

_REDIS_PING_TIMEOUT = 0.5  # fail fast - this must never make /health itself slow


def _database_status(db: DbSession) -> str:
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        return "unreachable"
    return "connected"


def _redis_status() -> str:
    """Only meaningful in queue mode - sync mode never touches Redis at all,
    same gate as ``app.services.progress``."""
    if get_settings().processing_mode != "queue":
        return "not_applicable"
    try:
        redis.Redis.from_url(
            get_settings().redis_url,
            socket_connect_timeout=_REDIS_PING_TIMEOUT,
            socket_timeout=_REDIS_PING_TIMEOUT,
        ).ping()
    except Exception:
        return "unreachable"
    return "connected"


@router.get("/health")
async def health(db: DbSession) -> JsonDict:
    """Report system health: DB connectivity, Redis (queue mode only), and how
    much room is left on the data volume - the folder-watch stacking mode is
    meant to run unattended for hours, so a filling disk should show up here
    before it shows up as an outage."""
    database_status = _database_status(db)
    return {
        "status": "healthy" if database_status == "connected" else "degraded",
        "version": __version__,
        "database": database_status,
        "redis": _redis_status(),
        "disk": volume_usage(),
        "timestamp": datetime.now(UTC).isoformat(),
    }
