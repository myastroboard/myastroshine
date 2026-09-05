"""Version and update-check endpoints.

GET /api/version                 - the version this instance is running
GET /api/version/check-updates   - latest GitHub release, cached ~4h
                                    (see app/services/version_check.py)
"""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.dependencies import RequireRateLimit, VersionCheckServiceDep
from app.types import JsonDict

router = APIRouter(tags=["system"])


@router.get("/version")
async def read_version() -> JsonDict:
    """The version currently running - a direct read, nothing to cache."""
    return {"version": __version__}


@router.get("/version/check-updates")
async def check_updates(
    versions: VersionCheckServiceDep, _rate_limit: RequireRateLimit
) -> JsonDict:
    """Latest GitHub release info, cached to stay well under GitHub's rate limit."""
    return await versions.check_for_updates()
