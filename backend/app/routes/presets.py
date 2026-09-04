"""Preset routes.

GET    /api/presets                                  - list presets
POST   /api/presets                                  - save a preset
DELETE /api/presets/{preset_id}                       - delete a user preset
POST   /api/presets/{preset_id}/apply/{session_id}    - apply a preset to a session
"""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.dependencies import EnhancementServiceDep, PresetServiceDep, RequireRateLimit
from app.exceptions import SessionNotFoundError
from app.logging_config import get_logger
from app.models import (
    PresetListResponse,
    ProcessingParameters,
    ProcessResponse,
    SavePresetRequest,
    SavePresetResponse,
)
from app.utils.rate_limit import get_client_ip
from app.utils.validators import is_valid_session_id

logger = get_logger(__name__)

router = APIRouter(prefix="/presets", tags=["presets"])


@router.get("", response_model=PresetListResponse)
async def list_presets(presets: PresetServiceDep) -> PresetListResponse:
    """Return available presets (built-in first, then user presets)."""
    items = presets.list_presets()
    return PresetListResponse(presets=items, total=len(items))


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SavePresetResponse)
async def save_preset(
    request: SavePresetRequest, presets: PresetServiceDep, _rate_limit: RequireRateLimit
) -> SavePresetResponse:
    """Create and store a new user preset."""
    record = presets.save_preset(
        name=request.name,
        parameters=request.parameters,
        description=request.description,
        category=request.category,
    )
    return SavePresetResponse(
        preset_id=record.preset_id,
        name=record.name,
        created_at=record.created_at,
    )


@router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preset(
    preset_id: str, presets: PresetServiceDep, _rate_limit: RequireRateLimit
) -> None:
    """Delete a user preset (built-in presets cannot be deleted)."""
    presets.delete_preset(preset_id)


@router.post("/{preset_id}/apply/{session_id}", response_model=ProcessResponse)
async def apply_preset(
    preset_id: str,
    session_id: str,
    presets: PresetServiceDep,
    enhancement: EnhancementServiceDep,
    http_request: Request,
    _rate_limit: RequireRateLimit,
) -> ProcessResponse:
    """Apply a preset's parameters to a session (shortcut for /process)."""
    if not is_valid_session_id(session_id):
        raise SessionNotFoundError(f"Session {session_id} not found")
    preset = presets.get_preset(preset_id)
    client_ip = get_client_ip(http_request)
    return enhancement.dispatch(session_id, ProcessingParameters(**preset.parameters), client_ip)
