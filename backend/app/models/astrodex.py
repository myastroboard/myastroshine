"""Request/response models for the MyAstroBoard AstroDex handoff."""

from __future__ import annotations

from pydantic import BaseModel

from app.models.image import Dimensions, HistogramData


class HandoffResumeRequest(BaseModel):
    """Body of ``POST /api/astrodex/handoff/resume``."""

    handoff: str


class HandoffResumeResponse(BaseModel):
    """The opened session, ready for the editor to load."""

    session_id: str
    image_url: str
    dimensions: Dimensions
    histogram: HistogramData
    object_name: str | None = None
    astrodex_item_id: str


class HandoffReturnRequest(BaseModel):
    """Body of ``POST /api/astrodex/handoff/return``."""

    session_id: str


class HandoffReturnResponse(BaseModel):
    """Delivery outcome of the enhanced image going back to AstroDex."""

    session_id: str
    status: str
    astrodex_item_id: str
