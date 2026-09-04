"""Stacking routes (v1.1).

POST /api/stack/initiate                  - open a stack session
POST /api/stack/{stack_id}/upload-frame   - upload one frame
POST /api/stack/{stack_id}/process        - register + normalise + combine
GET  /api/stack/{stack_id}                 - stack result and statistics

Processing runs inline (``PROCESSING_MODE=sync``) or on the Celery queue
(``PROCESSING_MODE=queue``); progress streams over
``/ws/stack-status/{job_id}``.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, Request, UploadFile, status

from app.db.models import StackRecord
from app.dependencies import JobServiceDep, RequireRateLimit, StackingServiceDep
from app.logging_config import get_logger
from app.models import (
    InitiateStackRequest,
    StackResultResponse,
    StackSessionResponse,
    StackStatistics,
    UploadFrameResponse,
)
from app.utils import image_utils
from app.utils.rate_limit import get_client_ip
from app.utils.validators import validate_upload_size

logger = get_logger(__name__)

router = APIRouter(prefix="/stack", tags=["stacking"])


def _result(record: StackRecord, job_id: str | None = None) -> StackResultResponse:
    session_id = record.session_id
    return StackResultResponse(
        stack_id=record.stack_id,
        status=record.status,
        job_id=job_id,
        ws_status_url=f"/ws/stack-status/{job_id}" if job_id else None,
        session_id=session_id,
        stacked_image_url=f"/api/preview/{session_id}?full=true" if session_id else None,
        statistics=StackStatistics(**record.result) if record.result else None,
        error=record.error,
    )


@router.post("/initiate", status_code=status.HTTP_202_ACCEPTED, response_model=StackSessionResponse)
async def initiate_stack(
    request: InitiateStackRequest, stacking: StackingServiceDep, _rate_limit: RequireRateLimit
) -> StackSessionResponse:
    """Open a stacking session and wait for frames."""
    record = stacking.initiate(request)
    return StackSessionResponse(
        stack_id=record.stack_id,
        status=record.status,
        frame_count=record.frame_count,
        received_frames=record.received_frames,
    )


@router.post(
    "/{stack_id}/upload-frame",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=UploadFrameResponse,
)
async def upload_frame(
    stack_id: str,
    stacking: StackingServiceDep,
    _rate_limit: RequireRateLimit,
    frame_index: int = Form(...),
    file: UploadFile = File(...),
) -> UploadFrameResponse:
    """Upload a single frame into an open stacking session."""
    data = await file.read()
    validate_upload_size(len(data))
    image = image_utils.decode_image(data)

    record = stacking.add_frame(stack_id, frame_index, image)
    return UploadFrameResponse(
        frame_index=frame_index,
        received_frames=record.received_frames,
        frame_count=record.frame_count,
        status=record.status,
    )


@router.post("/{stack_id}/process", response_model=StackResultResponse)
async def process_stack(
    stack_id: str,
    stacking: StackingServiceDep,
    jobs: JobServiceDep,
    http_request: Request,
    _rate_limit: RequireRateLimit,
) -> StackResultResponse:
    """Register, normalise, reject cosmic rays, and combine the frames."""
    record, job_id = stacking.dispatch(stack_id, jobs, get_client_ip(http_request))
    return _result(record, job_id)


@router.get("/{stack_id}", response_model=StackResultResponse)
async def get_stack(stack_id: str, stacking: StackingServiceDep) -> StackResultResponse:
    """Return the stack result and statistics."""
    return _result(stacking.get_result(stack_id))
