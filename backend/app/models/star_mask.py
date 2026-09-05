"""Star mask preview request/response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StarMaskRequest(BaseModel):
    """Body of ``POST /api/star-mask/{session_id}``."""

    sensitivity: int = Field(default=50, ge=0, le=100)
    max_size: int = Field(default=30, ge=0, le=100)


class StarSourceInfo(BaseModel):
    """One detected star, as fractions (0-1) of the analysed image's width/height."""

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    radius: float = Field(ge=0.0, le=1.0)


class StarMaskResponse(BaseModel):
    """Body of ``POST /api/star-mask/{session_id}``."""

    session_id: str
    source_count: int
    stars: list[StarSourceInfo]
