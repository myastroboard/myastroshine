"""AstroDex handoff routes.

POST /api/astrodex/handoff/resume  - open an editing session from a signed
                                     handoff token minted by MyAstroBoard.
POST /api/astrodex/handoff/return  - send the enhanced result back to AstroDex,
                                     where it is filed as a new picture.

Neither route uses a bearer token: the signed handoff token is the credential
(its ``kid`` selects the webhook token whose ``signing_secret`` verifies it).
See docs/API.md "AstroDex integration".
"""

from __future__ import annotations

from fastapi import APIRouter

from app.dependencies import AstroDexHandoffServiceDep, RequireRateLimit, StorageDep
from app.logging_config import get_logger
from app.models import (
    Dimensions,
    HandoffResumeRequest,
    HandoffResumeResponse,
    HandoffReturnRequest,
    HandoffReturnResponse,
    HistogramData,
)
from app.utils import image_utils

logger = get_logger(__name__)

router = APIRouter(prefix="/astrodex", tags=["astrodex"])


@router.post("/handoff/resume", response_model=HandoffResumeResponse)
async def resume_handoff(
    request: HandoffResumeRequest,
    handoff: AstroDexHandoffServiceDep,
    storage: StorageDep,
    _rate_limit: RequireRateLimit,
) -> HandoffResumeResponse:
    """Verify the handoff, pull the source image from AstroDex, open a session."""
    record, link = await handoff.resume(request.handoff)

    image = storage.load_original(record.session_id)
    height, width = image.shape[:2]
    return HandoffResumeResponse(
        session_id=record.session_id,
        image_url=f"/api/preview/{record.session_id}",
        dimensions=Dimensions(width=width, height=height),
        histogram=HistogramData(**image_utils.compute_histogram(image)),
        object_name=link.object_name,
        astrodex_item_id=link.astrodex_item_id,
    )


@router.post("/handoff/return", response_model=HandoffReturnResponse)
async def return_handoff(
    request: HandoffReturnRequest,
    handoff: AstroDexHandoffServiceDep,
    _rate_limit: RequireRateLimit,
) -> HandoffReturnResponse:
    """Sign and POST the enhanced image back to AstroDex."""
    link = await handoff.return_enhanced(request.session_id)
    logger.info(
        "enhanced image returned", session_id=request.session_id, status=link.webhook_status
    )
    return HandoffReturnResponse(
        session_id=request.session_id,
        status=link.webhook_status,
        astrodex_item_id=link.astrodex_item_id,
    )
