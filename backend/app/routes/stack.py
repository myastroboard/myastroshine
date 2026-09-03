"""Stacking routes (v1.1+).

POST /api/stack/initiate                     - open a stack session
POST /api/stack/{stack_id}/upload-frame      - upload one frame
POST /api/stack/{stack_id}/process           - align + combine the frames
GET  /api/stack/{stack_id}                    - stack result and statistics
Implemented in Sprints 6-7. The progress WebSocket lives in
``app.routes.websockets`` (/ws/stack-status/{job_id}).
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.logging_config import get_logger
from app.types import JsonDict

logger = get_logger(__name__)

router = APIRouter(prefix="/stack", tags=["stacking"])


class InitiateStackRequest(BaseModel):
    """Body of ``POST /api/stack/initiate``."""

    frame_count: int = Field(ge=2, le=100)
    combination_method: str = Field(default="median", pattern="^(median|mean|sigma_clip)$")
    cosmic_ray_rejection: bool = True
    background_normalization: bool = True
    registration_method: str = Field(default="orb", pattern="^(sift|orb)$")


@router.post("/initiate", status_code=status.HTTP_202_ACCEPTED)
async def initiate_stack(request: InitiateStackRequest) -> JsonDict:
    """Open a stacking session and wait for frames."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="stacking not implemented yet (Sprint 6)",
    )


@router.post("/{stack_id}/upload-frame", status_code=status.HTTP_202_ACCEPTED)
async def upload_frame(
    stack_id: str,
    frame_index: int = Form(...),
    file: UploadFile = File(...),
) -> JsonDict:
    """Upload a single frame into an open stacking session."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="stacking not implemented yet (Sprint 6)",
    )


@router.post("/{stack_id}/process", status_code=status.HTTP_202_ACCEPTED)
async def process_stack(stack_id: str) -> JsonDict:
    """Register, normalize, reject cosmic rays, and combine the frames."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="stacking not implemented yet (Sprint 7)",
    )


@router.get("/{stack_id}")
async def get_stack(stack_id: str) -> JsonDict:
    """Return the stack result and statistics."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="stacking not implemented yet (Sprint 7)",
    )
