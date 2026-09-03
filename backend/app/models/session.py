"""Session-related models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.processing import ProcessingParameters


class SessionInfo(BaseModel):
    """Public view of a processing session."""

    session_id: str
    created_at: datetime
    expires_at: datetime
    original_filename: str | None = None
    parameters: ProcessingParameters | None = None
    astrodex_image_id: str | None = None
