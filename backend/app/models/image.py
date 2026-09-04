"""Models describing images, their stats, and the upload response."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Dimensions(BaseModel):
    """Pixel dimensions of an image."""

    width: int = Field(gt=0)
    height: int = Field(gt=0)


class HistogramData(BaseModel):
    """Per-channel 256-bin histogram."""

    r: list[int]
    g: list[int]
    b: list[int]


class UploadResponse(BaseModel):
    """Returned by ``POST /api/upload``."""

    session_id: str
    image_url: str
    dimensions: Dimensions
    file_size_bytes: int
    histogram: HistogramData
    upload_timestamp: datetime
    expires_at: datetime
