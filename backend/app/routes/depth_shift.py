"""Depth shift (parallax) routes.

POST /api/depth-shift/{session_id}                 - generate depth map + layers
GET  /api/depth-shift/{session_id}/metadata        - depth statistics + layer URLs
GET  /api/depth-shift/{session_id}/depth_map       - the depth map as a PNG
GET  /api/depth-shift/{session_id}/layer_{index}   - a single BGRA parallax layer
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.dependencies import DepthShiftServiceDep
from app.exceptions import SessionNotFoundError
from app.logging_config import get_logger
from app.models import DepthMetadataResponse, DepthShiftRequest, DepthShiftResponse
from app.utils.validators import is_valid_session_id

logger = get_logger(__name__)

router = APIRouter(prefix="/depth-shift", tags=["depth-shift"])


def _require_session(session_id: str) -> None:
    if not is_valid_session_id(session_id):
        raise SessionNotFoundError(f"Session {session_id} not found")


@router.post("/{session_id}", response_model=DepthShiftResponse)
async def generate_depth_shift(
    session_id: str,
    request: DepthShiftRequest,
    depth_shift: DepthShiftServiceDep,
) -> DepthShiftResponse:
    """Generate the depth map and parallax layers for a session."""
    _require_session(session_id)
    return depth_shift.generate(session_id, request.num_layers)


@router.get("/{session_id}/metadata", response_model=DepthMetadataResponse)
async def depth_metadata(
    session_id: str, depth_shift: DepthShiftServiceDep
) -> DepthMetadataResponse:
    """Return depth-map statistics and the cached layer URLs."""
    _require_session(session_id)
    return depth_shift.metadata(session_id)


@router.get("/{session_id}/depth_map")
async def depth_map(session_id: str, depth_shift: DepthShiftServiceDep) -> FileResponse:
    """Return the depth map as a grayscale PNG."""
    _require_session(session_id)
    return FileResponse(depth_shift.depth_map_file(session_id), media_type="image/png")


@router.get("/{session_id}/layer_{index}")
async def depth_layer(
    session_id: str, index: int, depth_shift: DepthShiftServiceDep
) -> FileResponse:
    """Return a single parallax layer as a PNG with an alpha channel."""
    _require_session(session_id)
    return FileResponse(depth_shift.layer_file(session_id, index), media_type="image/png")
