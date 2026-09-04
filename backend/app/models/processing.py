"""Processing parameter model and process endpoint contracts.

Constraints mirror docs/API.md. Keep the two in sync.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GeometryParameters(BaseModel):
    """Framing applied before enhancement: rotate, flip, straighten, crop.

    Order: quarter rotations (clockwise), then flips, then straighten (the image
    is scaled up to keep the frame full), then the crop rectangle. Crop
    coordinates are fractions of the rotated/flipped image.
    """

    model_config = ConfigDict(extra="forbid")

    straighten: float = Field(default=0.0, ge=-45.0, le=45.0)
    rotate_quarters: int = Field(default=0, ge=0, le=3)
    flip_horizontal: bool = False
    flip_vertical: bool = False
    crop_x: float = Field(default=0.0, ge=0.0, le=1.0)
    crop_y: float = Field(default=0.0, ge=0.0, le=1.0)
    crop_w: float = Field(default=1.0, gt=0.0, le=1.0)
    crop_h: float = Field(default=1.0, gt=0.0, le=1.0)

    @model_validator(mode="after")
    def _crop_within_bounds(self) -> GeometryParameters:
        if self.crop_x + self.crop_w > 1.0 + 1e-6 or self.crop_y + self.crop_h > 1.0 + 1e-6:
            raise ValueError("crop rectangle extends past the image")
        return self


class ProcessingParameters(BaseModel):
    """Enhancement parameters applied by the processing pipeline.

    ``extra="forbid"``: an unknown key (e.g. a mis-cased ``depthShiftIntensity``)
    is a 400, not a silently-ignored field.
    """

    model_config = ConfigDict(extra="forbid")

    geometry: GeometryParameters = Field(default_factory=GeometryParameters)
    contrast: float = Field(default=1.0, ge=0.5, le=3.0)
    brightness: float = Field(default=0.0, ge=-1.0, le=1.0)
    saturation: float = Field(default=1.0, ge=0.0, le=2.0)
    highlights: float = Field(default=0.0, ge=-1.0, le=1.0)
    shadows: float = Field(default=0.0, ge=-1.0, le=1.0)
    clarity: float = Field(default=0.0, ge=-1.0, le=1.0)
    vibrance: float = Field(default=1.0, ge=0.0, le=2.0)
    denoise: int = Field(default=0, ge=0, le=100)
    star_reduction: int = Field(default=0, ge=0, le=100)
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
