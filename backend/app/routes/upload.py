"""Image upload and preview routes.

POST /api/upload            - validate an image, open a session
GET  /api/preview/{id}      - current preview JPEG (?full=true for full res)
"""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse

from app.dependencies import SessionServiceDep, StorageDep
from app.exceptions import SessionNotFoundError, UnsupportedImageError
from app.logging_config import get_logger
from app.models import Dimensions, HistogramData, UploadResponse
from app.utils import image_utils
from app.utils.validators import (
    is_valid_session_id,
    validate_image_extension,
    validate_upload_size,
)

logger = get_logger(__name__)

router = APIRouter(tags=["upload"])


@router.post("/upload", response_model=UploadResponse)
async def upload_image(
    sessions: SessionServiceDep,
    storage: StorageDep,
    file: UploadFile = File(...),
) -> UploadResponse:
    """Accept an image file and open a processing session."""
    data = await file.read()
    if not data:
        raise UnsupportedImageError("Empty upload")
    validate_upload_size(len(data))
    if file.filename:
        validate_image_extension(file.filename)

    image = image_utils.decode_image(data)
    height, width = image.shape[:2]

    record = sessions.create_session(image_path="", original_filename=file.filename)
    storage.save_original(record.session_id, image)
    record.image_path = str(storage.original_path(record.session_id))
    sessions.db.commit()

    logger.info(
        "image uploaded",
        session_id=record.session_id,
        width=width,
        height=height,
        bytes=len(data),
    )

    return UploadResponse(
        session_id=record.session_id,
        image_url=f"/api/preview/{record.session_id}",
        dimensions=Dimensions(width=width, height=height),
        file_size_bytes=len(data),
        histogram=HistogramData(**image_utils.compute_histogram(image)),
        upload_timestamp=record.created_at,
        expires_at=record.expires_at,
    )


@router.get("/preview/{session_id}")
async def get_preview(
    session_id: str,
    sessions: SessionServiceDep,
    storage: StorageDep,
    full: bool = False,
) -> FileResponse:
    """Return the current preview JPEG for a session."""
    if not is_valid_session_id(session_id):
        raise SessionNotFoundError(f"Session {session_id} not found")
    sessions.get_session(session_id)

    path = storage.processed_path(session_id) if full else storage.preview_path(session_id)
    if not path.exists():
        raise SessionNotFoundError(f"No preview for session {session_id}")

    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})
