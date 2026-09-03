"""Processing parameter model and process endpoint contracts.

Constraints mirror docs/API.md. Keep the two in sync.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProcessingParameters(BaseModel):
    """Enhancement parameters applied by the processing pipeline."""

    contrast: float = Field(default=1.0, ge=0.5, le=3.0)
    brightness: float = Field(default=0.0, ge=-1.0, le=1.0)
    saturation: float = Field(default=1.0, ge=0.0, le=2.0)
    highlights: float = Field(default=0.0, ge=-1.0, le=1.0)
    shadows: float = Field(default=0.0, ge=-1.0, le=1.0)
    clarity: float = Field(default=0.0, ge=-1.0, le=1.0)
    vibrance: float = Field(default=1.0, ge=0.0, le=2.0)
    denoise: int = Field(default=0, ge=0, le=100)
    sharpness: float = Field(default=1.0, ge=0.0, le=2.0)
    temperature: int = Field(default=6500, ge=2000, le=8000)
    tint: int = Field(default=0, ge=-50, le=50)
    depth_shift_intensity: int = Field(default=0, ge=-100, le=100)


class ProcessRequest(BaseModel):
    """Body of ``POST /api/process/{session_id}``."""

    parameters: ProcessingParameters
    apply_depth_shift: bool = False
    depth_shift_intensity: int = Field(default=0, ge=-100, le=100)


class ProcessResponse(BaseModel):
    """Returned by ``POST /api/process/{session_id}``."""

    session_id: str
    job_id: str
    status: str
    preview_url: str
    estimated_time_seconds: int
    ws_status_url: str
