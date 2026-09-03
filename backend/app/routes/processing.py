"""Image processing route.

POST /api/process/{session_id} - apply enhancement parameters.

Sprint 1 runs the pipeline synchronously and returns a completed job. Sprint 3
moves heavy work onto the Celery queue and streams progress over the WebSocket
in ``app.routes.websockets``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.dependencies import ProcessingServiceDep, SessionServiceDep, StorageDep
from app.exceptions import ImageProcessingError, SessionNotFoundError
from app.logging_config import get_logger
from app.models import ProcessRequest, ProcessResponse
from app.utils.validators import is_valid_session_id

logger = get_logger(__name__)

router = APIRouter(tags=["processing"])


@router.post("/process/{session_id}", response_model=ProcessResponse)
async def process_image(
    session_id: str,
    request: ProcessRequest,
    sessions: SessionServiceDep,
    storage: StorageDep,
    processing: ProcessingServiceDep,
) -> ProcessResponse:
    """Apply enhancement parameters to the session image."""
    if not is_valid_session_id(session_id):
        raise SessionNotFoundError(f"Session {session_id} not found")
    sessions.get_session(session_id)

    original = storage.load_original(session_id)
    try:
        result = processing.apply_parameters(original, request.parameters)
    except Exception as exc:
        logger.exception("processing failed", session_id=session_id)
        raise ImageProcessingError("Image processing failed") from exc

    storage.save_result(session_id, result)
    sessions.update_parameters(session_id, request.parameters.model_dump())

    job_id = f"sync-{uuid.uuid4().hex[:12]}"
    logger.info("image processed", session_id=session_id, job_id=job_id)

    return ProcessResponse(
        session_id=session_id,
        job_id=job_id,
        status="completed",
        preview_url=f"/api/preview/{session_id}",
        estimated_time_seconds=0,
        ws_status_url=f"/ws/processing-status/{job_id}",
    )
