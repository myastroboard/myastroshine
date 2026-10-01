"""Health check endpoint."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import text

from app import __version__
from app.dependencies import DbSession
from app.types import JsonDict
from app.utils.disk_usage import volume_usage

router = APIRouter(tags=["system"])


def _database_status(db: DbSession) -> str:
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        return "unreachable"
    return "connected"


@router.get("/health")
async def health(db: DbSession) -> JsonDict:
    """Report system health: DB connectivity and how much room is left on the
    data volume - the folder-watch stacking mode is meant to run unattended for
    hours, so a filling disk should show up here before it shows up as an outage."""
    database_status = _database_status(db)
    return {
        "status": "healthy" if database_status == "connected" else "degraded",
        "version": __version__,
        "database": database_status,
        "disk": volume_usage(),
        "timestamp": datetime.now(UTC).isoformat(),
    }
