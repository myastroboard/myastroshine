"""Stacking request/response models (linear rebuild).

See ``initial_plan/12_STACKING_REBUILD.md``. The v1.1 ``sift``/``orb`` +
``median``/``sigma_clip`` + cosmic-ray-toggle contract is replaced by a
transform model, a pixel-rejection algorithm, and a per-frame weighting mode.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RegistrationTransform = Literal["translation", "similarity", "affine"]
CombinationMethod = Literal["average", "median"]
RejectionAlgo = Literal["none", "sigma", "winsorized_sigma"]
Weighting = Literal["none", "noise", "quality"]
QualityFilter = Literal["off", "lenient", "moderate", "strict"]

_MAX_FRAMES = 5000  # hard ceiling; the operator's stacking_max_frames is the real gate


class InitiateStackRequest(BaseModel):
    """Body of ``POST /api/stack/initiate``."""

    frame_count: int = Field(ge=2, le=_MAX_FRAMES)
    registration_transform: RegistrationTransform = "similarity"
    combination_method: CombinationMethod = "average"
    rejection_algo: RejectionAlgo = "winsorized_sigma"
    weighting: Weighting = "noise"
    cosmetic_correction: bool = True
    quality_filter: QualityFilter = "moderate"
    post_process: bool = True


class ProcessStackRequest(BaseModel):
    """Optional body of ``POST /api/stack/{stack_id}/process``.

    Lets the user re-stack with a changed setting without re-uploading. Any field
    left out keeps the value chosen at ``initiate`` (or the previous run).
    """

    registration_transform: RegistrationTransform | None = None
    combination_method: CombinationMethod | None = None
    rejection_algo: RejectionAlgo | None = None
    weighting: Weighting | None = None
    cosmetic_correction: bool | None = None
    quality_filter: QualityFilter | None = None
    post_process: bool | None = None


class StackSessionResponse(BaseModel):
    """Returned by ``POST /api/stack/initiate`` and the upload endpoints."""

    stack_id: str
    status: str
    frame_count: int
    received_frames: int


class UploadFrameResponse(BaseModel):
    """Returned by ``POST /api/stack/{stack_id}/upload-frame``."""

    frame_index: int
    received_frames: int
    frame_count: int
    status: str


class FrameQualityInfo(BaseModel):
    """Per-frame quality metrics and the auto-reject verdict (Phase 3)."""

    star_count: int
    fwhm: float
    roundness: float
    background: float
    snr: float
    score: float  # 0..100
    weight: float  # relative integration weight, median frame ~= 1.0
    accepted: bool
    reject_reason: str | None = None  # "clouds" | "soft" | "trailed" | "bright_sky"


class StackFrameInfo(BaseModel):
    """One uploaded frame, for the frame grid in the UI."""

    index: int
    thumb_url: str
    excluded: bool
    quality: FrameQualityInfo | None = None


class ExcludeFrameRequest(BaseModel):
    """Body of ``POST /api/stack/{stack_id}/frame/{index}/exclude``."""

    excluded: bool


class CalibrationFrameCounts(BaseModel):
    """How many subs of each calibration kind the stack holds."""

    dark: int = 0
    flat: int = 0
    bias: int = 0
    dark_flat: int = 0


class CalibrationSummary(BaseModel):
    """Calibration state, returned with the stack and after a calibration upload."""

    frames: CalibrationFrameCounts
    cosmetic_correction: bool


class StackStatistics(BaseModel):
    """Summary of a completed stack."""

    frames_stacked: int
    frames_excluded: int
    frames_auto_rejected: int = 0
    combination_method: str
    registration_transform: str
    registration_rms_px: float | None = None
    reference_frame: int | None = None
    snr_improvement: float
    measured_noise_reduction: float | None = None
    calibrated: bool = False
    post_processed: bool = False


class StackResultResponse(BaseModel):
    """Returned by ``POST /api/stack/{stack_id}/process`` and ``GET /api/stack/{id}``."""

    stack_id: str
    status: str
    job_id: str | None = None
    ws_status_url: str | None = None
    session_id: str | None = None
    stacked_image_url: str | None = None
    statistics: StackStatistics | None = None
    frames: list[StackFrameInfo] = Field(default_factory=list)
    calibration: CalibrationSummary | None = None
    error: str | None = None
