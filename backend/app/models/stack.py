"""Stacking (v1.1) request/response models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RegistrationMethod = Literal["sift", "orb"]
CombinationMethod = Literal["median", "mean", "sigma_clip"]


class InitiateStackRequest(BaseModel):
    """Body of ``POST /api/stack/initiate``."""

    frame_count: int = Field(ge=2, le=100)
    registration_method: RegistrationMethod = "orb"
    combination_method: CombinationMethod = "median"
    cosmic_ray_rejection: bool = True
    background_normalization: bool = True


class StackSessionResponse(BaseModel):
    """Returned by ``POST /api/stack/initiate``."""

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


class StackStatistics(BaseModel):
    """Summary of a completed stack."""

    frames_stacked: int
    frames_rejected: int
    combination_method: str
    cosmic_rays_removed: int
    registration_success_rate: float
    snr_improvement: float


class StackResultResponse(BaseModel):
    """Returned by ``POST /api/stack/{stack_id}/process`` and ``GET /api/stack/{id}``."""

    stack_id: str
    status: str
    job_id: str | None = None
    ws_status_url: str | None = None
    session_id: str | None = None
    stacked_image_url: str | None = None
    statistics: StackStatistics | None = None
    error: str | None = None
