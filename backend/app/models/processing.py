"""Processing parameter model and process endpoint contracts.

Constraints mirror docs/API.md. Keep the two in sync.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

_LEVEL_MIN = 0
_LEVEL_MAX = 255
_MIN_CURVE_POINTS = 2


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


class CurvePoint(BaseModel):
    """One control point of the tone curve: input/output level, both 8-bit."""

    model_config = ConfigDict(extra="forbid")

    x: int = Field(ge=_LEVEL_MIN, le=_LEVEL_MAX)
    y: int = Field(ge=_LEVEL_MIN, le=_LEVEL_MAX)


class StackParameters(BaseModel):
    """The linear post-stack controls for a stacked-composite session.

    A stacked composite opens the editor on its 32-bit linear data; these run as
    a non-destructive pre-stage (``post_stack.render_stack_base``) ahead of the
    normal pipeline. ``stretch`` (0 = subtle .. 1 = aggressive) sets the
    auto-stretch target background; ``background_extraction`` (0 = off .. 100)
    is how much of the fitted low-order sky gradient to subtract;
    ``color_calibration`` neutralises the sky and balances the channels. All at
    their default on a fresh composite. Ignored for an ordinary single image.
    """

    model_config = ConfigDict(extra="forbid")

    stretch: float = Field(default=0.5, ge=0.0, le=1.0)
    background_extraction: int = Field(default=100, ge=0, le=100)
    color_calibration: bool = True


#: Fields removed from ``ProcessingParameters`` over time. Dropped on the way in
#: (see ``_drop_retired_keys``) so a stored preset / session parameter set from
#: an older version still loads instead of failing ``extra="forbid"``.
_RETIRED_KEYS = ("depth_shift_intensity",)


class ProcessingParameters(BaseModel):
    """Enhancement parameters applied by the processing pipeline.

    ``extra="forbid"``: a genuinely unknown key (e.g. a mis-cased
    ``depthShiftIntensity``) is a 400, not a silently-ignored field. Keys that
    this app used to define but has since removed (``_RETIRED_KEYS``) are the
    one exception - they are dropped rather than rejected.
    """

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _drop_retired_keys(cls, data: object) -> object:
        if isinstance(data, dict) and any(key in data for key in _RETIRED_KEYS):
            return {k: v for k, v in data.items() if k not in _RETIRED_KEYS}
        return data

    geometry: GeometryParameters = Field(default_factory=GeometryParameters)
    stack: StackParameters = Field(default_factory=StackParameters)
    contrast: float = Field(default=1.0, ge=0.5, le=3.0)
    exposure: float = Field(default=0.0, ge=-1.0, le=1.0)
    saturation: float = Field(default=1.0, ge=0.0, le=2.0)
    highlights: float = Field(default=0.0, ge=-1.0, le=1.0)
    shadows: float = Field(default=0.0, ge=-1.0, le=1.0)
    whites: float = Field(default=0.0, ge=-1.0, le=1.0)
    blacks: float = Field(default=0.0, ge=-1.0, le=1.0)
    clarity: float = Field(default=0.0, ge=-1.0, le=1.0)
    vibrance: float = Field(default=1.0, ge=0.0, le=2.0)
    denoise: int = Field(default=0, ge=0, le=100)
    chroma_denoise: int = Field(default=0, ge=0, le=100)
    vignette_correction: int = Field(default=0, ge=0, le=100)
    gradient_reduction: int = Field(default=0, ge=0, le=100)
    dehaze: int = Field(default=0, ge=0, le=100)
    star_reduction: int = Field(default=0, ge=0, le=100)
    star_sensitivity: int = Field(default=50, ge=0, le=100)
    star_max_size: int = Field(default=30, ge=0, le=100)
    # Starless (v0.3): when star_removal > 0 the pipeline splits - stars are
    # pulled out right after the background corrections, every creative stage
    # runs on the starless image, then star_recombine screen-blends the removed
    # star flux back at the end (0 = fully starless output, 100 = full strength).
    # Detection reuses star_sensitivity / star_max_size above.
    star_removal: int = Field(default=0, ge=0, le=100)
    star_recombine: int = Field(default=0, ge=0, le=100)
    sharpness: float = Field(default=1.0, ge=0.0, le=2.0)
    temperature: int = Field(default=6500, ge=2000, le=8000)
    tint: int = Field(default=0, ge=-50, le=50)
    curve_points: list[CurvePoint] = Field(default_factory=list)
    red_curve_points: list[CurvePoint] = Field(default_factory=list)
    green_curve_points: list[CurvePoint] = Field(default_factory=list)
    blue_curve_points: list[CurvePoint] = Field(default_factory=list)

    @model_validator(mode="after")
    def _curve_points_valid(self) -> ProcessingParameters:
        """Empty means "identity, no curve"; otherwise a full 0-255 function.

        Same rule for the master curve and each per-channel colour curve (see
        ``docs/ALGORITHMS.md`` "Tone curve" / "Colour curves").
        """
        for field_name in (
            "curve_points",
            "red_curve_points",
            "green_curve_points",
            "blue_curve_points",
        ):
            points: list[CurvePoint] = getattr(self, field_name)
            if not points:
                continue
            if len(points) < _MIN_CURVE_POINTS:
                raise ValueError(f"{field_name} needs at least 2 points, or none for no curve")
            if points[0].x != _LEVEL_MIN or points[-1].x != _LEVEL_MAX:
                raise ValueError(f"{field_name} must start at x=0 and end at x=255")
            xs = [p.x for p in points]
            if xs != sorted(xs) or len(set(xs)) != len(xs):
                raise ValueError(f"{field_name} must have strictly increasing x values")
        return self


class ProcessRequest(BaseModel):
    """Body of ``POST /api/process/{session_id}``."""

    parameters: ProcessingParameters


class ProcessResponse(BaseModel):
    """Returned by ``POST /api/process/{session_id}``."""

    session_id: str
    job_id: str
    status: str
    preview_url: str
    estimated_time_seconds: int
    ws_status_url: str
