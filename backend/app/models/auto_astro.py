"""Auto Astro response model."""

from __future__ import annotations

from pydantic import BaseModel

from app.models.processing import ProcessingParameters


class AutoAstroResponse(BaseModel):
    """Body of ``POST /api/auto-astro/{session_id}``.

    Same shape as ``ProcessResponse`` plus the computed ``parameters`` - unlike
    a preset apply, the frontend has no prior copy of these to sync sliders
    from, since they're derived from this specific image.
    """

    session_id: str
    job_id: str
    status: str
    preview_url: str
    estimated_time_seconds: int
    ws_status_url: str
    parameters: ProcessingParameters
