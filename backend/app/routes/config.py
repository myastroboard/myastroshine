"""Public client configuration.

GET /api/config - the handful of runtime settings the web UI needs *before* a
session exists (the upload size cap, the stacking limits). Non-sensitive, so
unlike ``/api/admin/app-settings`` it needs no ``ADMIN_ENABLED`` gate.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.utils.app_settings import get_app_settings

router = APIRouter(tags=["system"])


class PublicConfig(BaseModel):
    """Client-relevant slice of the runtime settings."""

    max_image_size_mb: int
    stacking_enabled: bool
    stacking_max_frames: int


@router.get("/config", response_model=PublicConfig)
async def read_config() -> PublicConfig:
    """Runtime limits the UI shows and pre-checks against.

    A trivial in-memory read called once per page load - not rate-limited,
    same as ``GET /version`` / ``GET /health``.
    """
    settings = get_app_settings()
    return PublicConfig(
        max_image_size_mb=settings.max_image_size_mb,
        stacking_enabled=settings.stacking_enabled,
        stacking_max_frames=settings.stacking_max_frames,
    )
