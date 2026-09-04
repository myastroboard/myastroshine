"""Image processing route.

POST /api/process/{session_id} - apply enhancement parameters.

Runs inline (``PROCESSING_MODE=sync``) or on the Celery queue
(``PROCESSING_MODE=queue``); either way progress is on the WebSocket in
``app.routes.websockets`` (/ws/processing-status/{job_id}).
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.dependencies import EnhancementServiceDep, RequireRateLimit
from app.exceptions import SessionNotFoundError
from app.logging_config import get_logger
from app.models import ProcessRequest, ProcessResponse
from app.utils.rate_limit import get_client_ip
from app.utils.validators import is_valid_session_id

logger = get_logger(__name__)

router = APIRouter(tags=["processing"])


@router.post("/process/{session_id}", response_model=ProcessResponse)
async def process_image(
    session_id: str,
    body: ProcessRequest,
    enhancement: EnhancementServiceDep,
    http_request: Request,
    _rate_limit: RequireRateLimit,
) -> ProcessResponse:
    """Apply enhancement parameters to the session image."""
    if not is_valid_session_id(session_id):
        raise SessionNotFoundError(f"Session {session_id} not found")
    return enhancement.dispatch(session_id, body.parameters, get_client_ip(http_request))
