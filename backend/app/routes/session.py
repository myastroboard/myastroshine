"""Session-scoped routes not owned by a more specific router.

GET /api/session/{session_id}/capture-info - acquisition info read off the
source FITS header(s), for the editor's capture info panel.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.dependencies import SessionServiceDep, StackingServiceDep
from app.exceptions import SessionNotFoundError
from app.models import CaptureInfo
from app.utils.validators import is_valid_session_id

router = APIRouter(tags=["session"])


@router.get("/session/{session_id}/capture-info", response_model=CaptureInfo | None)
async def get_capture_info(
    session_id: str,
    sessions: SessionServiceDep,
    stacking: StackingServiceDep,
) -> CaptureInfo | None:
    """The session's capture info, or ``None`` for a plain photo / bare header."""
    if not is_valid_session_id(session_id):
        raise SessionNotFoundError(f"Session {session_id} not found")
    sessions.get_session(session_id)  # 404/410 before touching the stack table

    info = stacking.get_capture_info(session_id)
    return CaptureInfo.model_validate(info) if info else None
