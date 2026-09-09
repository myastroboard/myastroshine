"""Public client configuration.

GET /api/config - the handful of runtime settings the web UI needs *before* a
session exists (the upload size cap, the stacking limits, which processing engines
are available). Non-sensitive, so unlike ``/api/admin/app-settings`` it needs no
``ADMIN_ENABLED`` gate.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.engine_probe import get_engine_statuses
from app.utils.app_settings import get_app_settings

router = APIRouter(tags=["system"])


class PublicConfig(BaseModel):
    """Client-relevant slice of the runtime settings."""

    max_image_size_mb: int
    stacking_enabled: bool
    stacking_max_frames: int
    #: Star-removal engines the editor may offer. Always contains ``"classic"``;
    #: ``"starnet2"`` is appended only when the operator has a working binary
    #: configured (initial_plan/13_EXTERNAL_ML_ENGINES.md).
    starless_engines: list[str]
    #: Denoise engines, same rule - ``"classic"`` always, ``"deepsnr"`` when found.
    denoise_engines: list[str]


@router.get("/config", response_model=PublicConfig)
async def read_config() -> PublicConfig:
    """Runtime limits the UI shows and pre-checks against.

    A trivial in-memory read called once per page load - not rate-limited,
    same as ``GET /version`` / ``GET /health``. The engine probe behind
    ``starless_engines`` / ``denoise_engines`` is memoised and a no-op unless the
    operator configured an engine path.
    """
    settings = get_app_settings()
    engines = get_engine_statuses()
    return PublicConfig(
        max_image_size_mb=settings.max_image_size_mb,
        stacking_enabled=settings.stacking_enabled,
        stacking_max_frames=settings.stacking_max_frames,
        starless_engines=["classic", *(["starnet2"] if engines["starnet2"].found else [])],
        denoise_engines=["classic", *(["deepsnr"] if engines["deepsnr"].found else [])],
    )
