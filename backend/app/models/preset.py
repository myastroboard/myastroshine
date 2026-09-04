"""Preset request/response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.processing import ProcessingParameters


class PresetOut(BaseModel):
    """A preset as returned by the API."""

    preset_id: str
    name: str
    category: str
    description: str | None = None
    parameters: ProcessingParameters
    author: str
    is_favorite: bool = False


class PresetListResponse(BaseModel):
    """Body of ``GET /api/presets``."""

    presets: list[PresetOut]
    total: int


class SavePresetRequest(BaseModel):
    """Body of ``POST /api/presets``."""

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    category: str = "astronomy"
    parameters: ProcessingParameters


class SavePresetResponse(BaseModel):
    """Body returned by ``POST /api/presets``."""

    preset_id: str
    name: str
    created_at: datetime
