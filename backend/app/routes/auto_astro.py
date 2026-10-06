"""Auto Astro route.

POST /api/auto-astro/{session_id} - analyse the session's original image and
apply a computed one-click parameter set (shortcut for /process, like preset
apply, but the parameters are derived from this image rather than fixed).
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.dependencies import (
    AutoAstroServiceDep,
    EnhancementServiceDep,
    RequireRateLimit,
    SessionServiceDep,
    StorageDep,
)
from app.exceptions import SessionNotFoundError
from app.logging_config import get_logger
from app.models import AutoAstroResponse, ProcessingParameters
from app.utils.rate_limit import get_client_ip
from app.utils.validators import is_valid_session_id

logger = get_logger(__name__)

router = APIRouter(tags=["auto-astro"])


@router.post("/auto-astro/{session_id}", response_model=AutoAstroResponse)
def apply_auto_astro(
    session_id: str,
    auto_astro: AutoAstroServiceDep,
    enhancement: EnhancementServiceDep,
    sessions: SessionServiceDep,
    storage: StorageDep,
    http_request: Request,
    _rate_limit: RequireRateLimit,
) -> AutoAstroResponse:
    """Analyse the original image and apply the resulting parameters.

    ``def``, not ``async``: the work is CPU-bound, so FastAPI runs it in its
    threadpool instead of stalling the event loop (WebSockets, health).
    """
    if not is_valid_session_id(session_id):
        raise SessionNotFoundError(f"Session {session_id} not found")

    session = sessions.get_session(session_id)  # 404/410 before touching storage
    image = storage.load_original(session_id)
    parameters = auto_astro.suggest_parameters(image)

    # Auto Astro proposes tone and star settings; framing (crop / rotate /
    # straighten / flip) is composition and the "Style" look a final choice, so
    # carry both through rather than silently resetting the user's crop or look.
    if session.parameters:
        current = ProcessingParameters.model_validate(session.parameters)
        parameters = parameters.model_copy(
            update={"geometry": current.geometry, "look": current.look}
        )

    client_ip = get_client_ip(http_request)
    result = enhancement.dispatch(session_id, parameters, client_ip)
    logger.info("auto astro applied", session_id=session_id)
    return AutoAstroResponse(**result.model_dump(), parameters=parameters)
