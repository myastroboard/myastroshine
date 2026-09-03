"""Health check endpoint."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from app import __version__
from app.types import JsonDict

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> JsonDict:
    """Report basic system health."""
    return {
        "status": "healthy",
        "version": __version__,
        "database": "connected",
        "timestamp": datetime.now(UTC).isoformat(),
    }
