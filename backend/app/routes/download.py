"""Download route.

POST /api/download/{session_id} - return the processed image as a file.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.dependencies import SessionServiceDep, StorageDep
from app.exceptions import SessionNotFoundError
from app.logging_config import get_logger
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


@router.post("/download/{session_id}")
async def download_image(
    session_id: str,
    request: DownloadRequest,
    sessions: SessionServiceDep,
    storage: StorageDep,
) -> Response:
    """Return the enhanced image as a downloadable file."""
    if not is_valid_session_id(session_id):
        raise SessionNotFoundError(f"Session {session_id} not found")
    sessions.get_session(session_id)

    image = storage.load_processed(session_id)
    body = image_utils.encode_image(image, request.format, request.quality)
    filename = f"myastroshine_{session_id[:8]}.{_EXT[request.format]}"

    logger.info("image downloaded", session_id=session_id, format=request.format)
    return Response(
        content=body,
        media_type=_MEDIA_TYPE[request.format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
