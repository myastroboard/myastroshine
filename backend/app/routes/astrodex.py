"""AstroDex integration routes.

POST /api/astrodex/receive   - receive an image + callback info from AstroDex
POST /api/send-to-astrodex   - send the enhanced image back via signed webhook
Implemented in Sprint 4.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.logging_config import get_logger
from app.types import JsonDict

logger = get_logger(__name__)

router = APIRouter(tags=["astrodex"])


class SendToAstroDexRequest(BaseModel):
    """Body of ``POST /api/send-to-astrodex``."""

    session_id: str
    astrodex_image_id: str
    parameters_used: JsonDict
    astrodex_callback_url: str


@router.post("/astrodex/receive")
async def receive_from_astrodex(
    image_id: str = Form(...),
    image: UploadFile = File(...),
    metadata: str = Form(...),
    callback_url: str = Form(...),
    callback_token: str = Form(...),
) -> JsonDict:
    """Receive an image pushed from AstroDex and open a session."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="astrodex receive not implemented yet (Sprint 4)",
    )


@router.post("/send-to-astrodex", status_code=status.HTTP_202_ACCEPTED)
async def send_to_astrodex(request: SendToAstroDexRequest) -> JsonDict:
    """Queue a signed webhook delivering the enhanced image to AstroDex."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="send to astrodex not implemented yet (Sprint 4)",
    )
