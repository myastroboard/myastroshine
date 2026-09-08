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

_MAX_FRAMES = 5000  # hard ceiling; the operator's stacking_max_frames is the real gate


class InitiateStackRequest(BaseModel):
    """Body of ``POST /api/stack/initiate``."""

    frame_count: int = Field(ge=2, le=_MAX_FRAMES)
    registration_transform: RegistrationTransform = "similarity"
    combination_method: CombinationMethod = "average"
    rejection_algo: RejectionAlgo = "winsorized_sigma"
    weighting: Weighting = "noise"


class ProcessStackRequest(BaseModel):
    """Optional body of ``POST /api/stack/{stack_id}/process``.

    Lets the user re-stack with a changed setting without re-uploading. Any field
    left out keeps the value chosen at ``initiate`` (or the previous run).
    """

    registration_transform: RegistrationTransform | None = None
    combination_method: CombinationMethod | None = None
    rejection_algo: RejectionAlgo | None = None
    weighting: Weighting | None = None


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


class StackFrameInfo(BaseModel):
    """One uploaded frame, for the frame grid in the UI."""

    index: int
    thumb_url: str
    excluded: bool


class ExcludeFrameRequest(BaseModel):
    """Body of ``POST /api/stack/{stack_id}/frame/{index}/exclude``."""

    excluded: bool


class StackStatistics(BaseModel):
    """Summary of a completed stack."""

    frames_stacked: int
    frames_excluded: int
    combination_method: str
    registration_transform: str
    registration_rms_px: float | None = None
    reference_frame: int | None = None
    snr_improvement: float
    measured_noise_reduction: float | None = None


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
    error: str | None = None
