"""Preset routes.

GET  /api/presets                                  - list presets
POST /api/presets                                  - save a preset
POST /api/presets/{preset_id}/apply/{session_id}   - apply a preset to a session
Implemented in Sprint 3.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.logging_config import get_logger
from app.models import ProcessingParameters
from app.types import JsonDict

logger = get_logger(__name__)

router = APIRouter(prefix="/presets", tags=["presets"])


class SavePresetRequest(BaseModel):
    """Body of ``POST /api/presets``."""

    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    category: str = "astronomy"
    parameters: ProcessingParameters


@router.get("")
async def list_presets() -> JsonDict:
    """Return available presets (system defaults + user presets)."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="presets not implemented yet (Sprint 3)",
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def save_preset(request: SavePresetRequest) -> JsonDict:
    """Create and store a new preset."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="presets not implemented yet (Sprint 3)",
    )


@router.post("/{preset_id}/apply/{session_id}")
async def apply_preset(preset_id: str, session_id: str) -> JsonDict:
    """Apply a preset's parameters to a session (shortcut for /process)."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="presets not implemented yet (Sprint 3)",
    )
