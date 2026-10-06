"""Looks routes - the "Style" step's catalogue and gallery thumbnails.

GET /api/looks/{session_id} - the looks offered for this session, grouped by
kind of picture: the night-landscape group first when its image has a sky
mask, then the general, nebula, galaxy, star-cluster, Moon and planet groups.

GET /api/looks/{session_id}/thumbnail - the current edit, before its look, with
``look`` (optional) applied at ``amount``, as a small JPEG.

The thumbnails are rendered from the session's stored pre-look thumbnail
(``StorageService.save_prelook``), so they cost milliseconds and never re-run
the pipeline. Every look's radii are relative to the image size, so a thumbnail
shows the same look as the full-resolution export (``app.services.looks``).
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.dependencies import (
    EnhancementServiceDep,
    ProcessingServiceDep,
    SessionServiceDep,
    StorageDep,
)
from app.exceptions import SessionNotFoundError
from app.models import LookCatalog, LookGroup, LookId, LookParameters, ProcessingParameters
from app.services.looks import (
    CLUSTER_LOOKS,
    GALAXY_LOOKS,
    GENERAL_LOOKS,
    MOON_LOOKS,
    NEBULA_LOOKS,
    NIGHTSCAPE_LOOKS,
    PLANET_LOOKS,
)
from app.utils import image_utils
from app.utils.validators import is_valid_session_id

router = APIRouter(tags=["looks"])

_THUMB_QUALITY = 85


@router.get("/looks/{session_id}", response_model=LookCatalog)
async def look_catalog(
    session_id: str,
    sessions: SessionServiceDep,
    enhancement: EnhancementServiceDep,
) -> LookCatalog:
    """Which looks the gallery offers for this session, grouped, in display order."""
    if not is_valid_session_id(session_id):
        raise SessionNotFoundError(f"Session {session_id} not found")
    sessions.get_session(session_id)
    groups = [
        LookGroup(scene="general", looks=list(GENERAL_LOOKS)),
        LookGroup(scene="nebula", looks=list(NEBULA_LOOKS)),
        LookGroup(scene="galaxy", looks=list(GALAXY_LOOKS)),
        LookGroup(scene="cluster", looks=list(CLUSTER_LOOKS)),
        LookGroup(scene="moon", looks=list(MOON_LOOKS)),
        LookGroup(scene="planet", looks=list(PLANET_LOOKS)),
    ]
    if enhancement.has_sky_mask(session_id):
        night = LookGroup(scene="nightscape", looks=list(NIGHTSCAPE_LOOKS))
        return LookCatalog(scene="nightscape", groups=[night, *groups])
    return LookCatalog(scene="general", groups=groups)


@router.get("/looks/{session_id}/thumbnail")
async def look_thumbnail(
    session_id: str,
    sessions: SessionServiceDep,
    storage: StorageDep,
    processing: ProcessingServiceDep,
    enhancement: EnhancementServiceDep,
    look: LookId | None = None,
    amount: int = Query(default=60, ge=0, le=100),
) -> Response:
    """The session's pre-look result with ``look`` at ``amount`` (none: as is)."""
    if not is_valid_session_id(session_id):
        raise SessionNotFoundError(f"Session {session_id} not found")
    record = sessions.get_session(session_id)

    source = storage.load_prelook_thumb(session_id)
    if source is None:
        # Never rendered since upload: the stored preview is the untouched,
        # look-free image.
        path = storage.preview_path(session_id)
        if not path.exists():
            raise SessionNotFoundError(f"No preview for session {session_id}")
        source = image_utils.load_image(path)

    geometry = ProcessingParameters.model_validate(record.parameters or {}).geometry
    sky = enhancement.look_sky_mask(session_id, look, geometry, source.shape[:2])
    result = processing.apply_look(source, LookParameters(look_id=look, amount=amount), sky)
    body = image_utils.encode_image(result, "jpeg", _THUMB_QUALITY)
    return Response(content=body, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})
