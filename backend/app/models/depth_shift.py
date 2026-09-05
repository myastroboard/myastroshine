"""Depth shift (parallax) request/response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FocusPoint(BaseModel):
    """Normalised focus point (0-1 on each axis, image space)."""

    x: float = Field(default=0.5, ge=0.0, le=1.0)
    y: float = Field(default=0.5, ge=0.0, le=1.0)


class DepthShiftRequest(BaseModel):
    """Body of ``POST /api/depth-shift/{session_id}``."""

    intensity: int = Field(default=50, ge=0, le=100)
    # None (the default) means "no focal point chosen" - purely gradient-based
    # depth, unchanged from before this field did anything. (0.5, 0.5) is a
    # real, deliberately-picked center and must stay distinguishable from
    # "not set", so this can't default to a concrete FocusPoint.
    focus_point: FocusPoint | None = None
    num_layers: int = Field(default=7, ge=2, le=12)


class DepthLayerInfo(BaseModel):
    """One parallax layer, ordered far (0) to near."""

    layer_id: int
    depth_range: tuple[float, float]
    image_url: str


class DepthStatistics(BaseModel):
    """Summary of the generated depth map."""

    min_depth: int
    max_depth: int
    mean_depth: int
    median_depth: int
    bright_areas_percent: float


class DepthShiftResponse(BaseModel):
    """Body of ``POST /api/depth-shift/{session_id}``."""

    session_id: str
    num_layers: int
    depth_map_url: str
    depth_layers: list[DepthLayerInfo]
    statistics: DepthStatistics


class DepthMetadataResponse(BaseModel):
    """Body of ``GET /api/depth-shift/{session_id}/metadata``."""

    session_id: str
    depth_map_generated: bool
    recommended_num_layers: int = 7
    statistics: DepthStatistics | None = None
    layer_urls: list[str] = []
