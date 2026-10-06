"""Download route.

POST /api/download/{session_id} - return the processed image as a file.

With a "Style" look active, the file carries the look by default and names it in
its metadata; ``style: false`` returns the same edit without the look.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.dependencies import RequireRateLimit, SessionServiceDep, StorageDep
from app.exceptions import SessionNotFoundError
from app.logging_config import get_logger
from app.models import LookParameters
from app.services.looks import look_description
from app.utils import image_utils
from app.utils.validators import is_valid_session_id

logger = get_logger(__name__)

router = APIRouter(tags=["download"])

_MEDIA_TYPE = {"jpeg": "image/jpeg", "png": "image/png", "tiff": "image/tiff"}
_EXT = {"jpeg": "jpg", "png": "png", "tiff": "tif"}


class DownloadRequest(BaseModel):
    """Body of ``POST /api/download/{session_id}``."""

    format: str = Field(default="jpeg", pattern="^(jpeg|png|tiff)$")
    quality: int = Field(default=95, ge=1, le=100)
    #: With a look active: ``True`` (default) exports it, ``False`` exports the
    #: same edit without it. Ignored when there is no look.
    style: bool = True


@router.post("/download/{session_id}")
async def download_image(
    session_id: str,
    request: DownloadRequest,
    sessions: SessionServiceDep,
    storage: StorageDep,
    _rate_limit: RequireRateLimit,
) -> Response:
    """Return the enhanced image as a downloadable file."""
    if not is_valid_session_id(session_id):
        raise SessionNotFoundError(f"Session {session_id} not found")
    record = sessions.get_session(session_id)

    look = LookParameters.model_validate((record.parameters or {}).get("look") or {})
    description = look_description(look)
    prelook = storage.load_prelook(session_id) if description and not request.style else None
    if prelook is not None:
        image, description = prelook, None
    else:
        image = storage.load_processed(session_id)
    body = image_utils.encode_image_described(image, request.format, request.quality, description)
    filename = f"myastroshine_{session_id[:8]}.{_EXT[request.format]}"

    logger.info(
        "image downloaded",
        session_id=session_id,
        format=request.format,
        style=look.look_id if description else None,
    )
    return Response(
        content=body,
        media_type=_MEDIA_TYPE[request.format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
