"""AstroDex integration routes.

POST /api/astrodex/receive   - receive an image + callback info from AstroDex
POST /api/send-to-astrodex   - queue a signed webhook back to AstroDex

Both require a valid webhook token (``Authorization: Bearer <token>``), created
from the UI (see /api/tokens).
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile, status
from pydantic import BaseModel

from app.dependencies import AstroDexDispatchDep, RequireRateLimit, RequireToken
from app.exceptions import UnsupportedImageError
from app.logging_config import get_logger
from app.services.astrodex_dispatch import deliver_webhook
from app.types import JsonDict
from app.utils import image_utils
from app.utils.validators import validate_upload_size

logger = get_logger(__name__)

router = APIRouter(tags=["astrodex"])


class SendToAstroDexRequest(BaseModel):
    """Body of ``POST /api/send-to-astrodex``."""

    session_id: str
    astrodex_image_id: str
    astrodex_callback_url: str


@router.post("/astrodex/receive", status_code=status.HTTP_201_CREATED)
async def receive_from_astrodex(
    token: RequireToken,
    dispatch: AstroDexDispatchDep,
    _rate_limit: RequireRateLimit,
    image_id: str = Form(...),
    image: UploadFile = File(...),
    callback_url: str = Form(...),
    callback_token: str | None = Form(default=None),
) -> JsonDict:
    """Receive an image pushed from AstroDex and open a session for it."""
    data = await image.read()
    if not data:
        raise UnsupportedImageError("Empty image upload")
    validate_upload_size(len(data))
    decoded = image_utils.decode_image(data)

    link = dispatch.receive_image(
        token=token,
        astrodex_image_id=image_id,
        image=decoded,
        callback_url=callback_url,
        callback_token=callback_token,
    )
    return {
        "session_id": link.session_id,
        "image_url": f"/api/preview/{link.session_id}",
        "astrodex_image_id": link.astrodex_image_id,
    }


@router.post("/send-to-astrodex", status_code=status.HTTP_202_ACCEPTED)
async def send_to_astrodex(
    request: SendToAstroDexRequest,
    token: RequireToken,
    dispatch: AstroDexDispatchDep,
    background: BackgroundTasks,
    _rate_limit: RequireRateLimit,
) -> JsonDict:
    """Queue a signed ``image_enhanced`` webhook to AstroDex."""
    link = dispatch.queue_send(
        session_id=request.session_id,
        astrodex_image_id=request.astrodex_image_id,
        callback_url=request.astrodex_callback_url,
        signing_token=token,
    )
    background.add_task(deliver_webhook, link.id)
    logger.info("webhook queued", session_id=request.session_id, link_id=link.id)
    return {
        "session_id": link.session_id,
        "webhook_id": f"webhook_{link.id}",
        "status": "pending",
        "message": "Webhook queued for delivery to AstroDex",
    }
