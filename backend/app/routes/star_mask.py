"""Star mask preview route.

POST /api/star-mask/{session_id} - detect stars in the session's cached
preview image and report their positions for a client-side mask overlay.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.dependencies import RequireRateLimit, StarMaskServiceDep
from app.exceptions import SessionNotFoundError
from app.logging_config import get_logger
from app.models import StarMaskRequest, StarMaskResponse
from app.utils.validators import is_valid_session_id

logger = get_logger(__name__)

router = APIRouter(tags=["star-mask"])


@router.post("/star-mask/{session_id}", response_model=StarMaskResponse)
async def detect_stars(
    session_id: str,
    body: StarMaskRequest,
    star_mask: StarMaskServiceDep,
    _rate_limit: RequireRateLimit,
) -> StarMaskResponse:
    """Detect stars in the session's preview image for a mask overlay."""
    if not is_valid_session_id(session_id):
        raise SessionNotFoundError(f"Session {session_id} not found")
    return star_mask.preview(session_id, body.sensitivity, body.max_size)
