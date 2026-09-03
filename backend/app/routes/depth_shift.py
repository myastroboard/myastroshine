"""Depth shift (parallax) routes.

POST /api/depth-shift/{session_id}                 - generate depth map + layers
GET  /api/depth-shift/{session_id}/metadata        - depth statistics
GET  /api/depth-shift/{session_id}/layer_{index}   - individual layer PNG
Implemented in Sprint 4.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.logging_config import get_logger
from app.types import JsonDict

logger = get_logger(__name__)

router = APIRouter(prefix="/depth-shift", tags=["depth-shift"])


class FocusPoint(BaseModel):
    """Normalized focus point (0-1 in each axis)."""

    x: float = Field(default=0.5, ge=0.0, le=1.0)
    y: float = Field(default=0.5, ge=0.0, le=1.0)


class DepthShiftRequest(BaseModel):
    """Body of ``POST /api/depth-shift/{session_id}``."""

    intensity: int = Field(default=50, ge=0, le=100)
    focus_point: FocusPoint = Field(default_factory=FocusPoint)
    num_layers: int = Field(default=7, ge=2, le=12)


@router.post("/{session_id}")
async def generate_depth_shift(session_id: str, request: DepthShiftRequest) -> JsonDict:
    """Generate the depth map and parallax layers for a session."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="depth shift not implemented yet (Sprint 4)",
    )


@router.get("/{session_id}/metadata")
async def depth_metadata(session_id: str) -> JsonDict:
    """Return depth map statistics and layer URLs."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="depth shift not implemented yet (Sprint 4)",
    )


@router.get("/{session_id}/layer_{index}")
async def depth_layer(session_id: str, index: int) -> None:
    """Return a single parallax layer as a PNG with alpha."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="depth shift not implemented yet (Sprint 4)",
    )
