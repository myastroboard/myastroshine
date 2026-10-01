"""FastAPI dependency wiring.

Routes depend on these annotated types; nothing here contains business logic.
"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import ADMIN_COOKIE_NAME
from app.db.database import get_db
from app.db.models import AdminSession, WebhookToken
from app.exceptions import AdminSetupRequiredError, ForbiddenError, UnauthorizedError
from app.logging_config import get_logger
from app.services.admin_auth import AdminAuthService
from app.services.astrodex_handoff import AstroDexHandoffService
from app.services.auto_astro import AutoAstroService
from app.services.depth_map import DepthMapService
from app.services.depth_shift import DepthShiftService
from app.services.enhancement import EnhancementService
from app.services.image_processing import ImageProcessingService
from app.services.job import JobService
from app.services.preset import PresetService
from app.services.session import SessionService
from app.services.stacking import StackingService
from app.services.star_detection import StarDetectionService
from app.services.star_mask import StarMaskService
from app.services.storage import StorageService
from app.services.token import TokenService
from app.services.version_check import VersionCheckService
from app.utils.app_settings import get_app_settings
from app.utils.rate_limit import enforce_request_rate_limit

logger = get_logger(__name__)

DbSession = Annotated[Session, Depends(get_db)]


def get_storage() -> StorageService:
    return StorageService()


StorageDep = Annotated[StorageService, Depends(get_storage)]


def get_session_service(db: DbSession, storage: StorageDep) -> SessionService:
    return SessionService(db, storage)


def get_processing_service() -> ImageProcessingService:
    return ImageProcessingService()


SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
ProcessingServiceDep = Annotated[ImageProcessingService, Depends(get_processing_service)]


def get_job_service(db: DbSession) -> JobService:
    return JobService(db)


JobServiceDep = Annotated[JobService, Depends(get_job_service)]


def get_enhancement_service(
    sessions: SessionServiceDep,
    storage: StorageDep,
    processing: ProcessingServiceDep,
    jobs: JobServiceDep,
) -> EnhancementService:
    return EnhancementService(sessions, storage, processing, jobs)


def get_preset_service(db: DbSession) -> PresetService:
    return PresetService(db)


def get_depth_shift_service(sessions: SessionServiceDep, storage: StorageDep) -> DepthShiftService:
    return DepthShiftService(sessions, storage, DepthMapService())


def get_star_mask_service(sessions: SessionServiceDep, storage: StorageDep) -> StarMaskService:
    return StarMaskService(sessions, storage, StarDetectionService())


def get_auto_astro_service() -> AutoAstroService:
    return AutoAstroService(StarDetectionService())


EnhancementServiceDep = Annotated[EnhancementService, Depends(get_enhancement_service)]
PresetServiceDep = Annotated[PresetService, Depends(get_preset_service)]
DepthShiftServiceDep = Annotated[DepthShiftService, Depends(get_depth_shift_service)]
StarMaskServiceDep = Annotated[StarMaskService, Depends(get_star_mask_service)]
AutoAstroServiceDep = Annotated[AutoAstroService, Depends(get_auto_astro_service)]


def get_token_service(db: DbSession) -> TokenService:
    return TokenService(db)


TokenServiceDep = Annotated[TokenService, Depends(get_token_service)]

_bearer = HTTPBearer(auto_error=False, description="Webhook token")


def require_token(
    tokens: TokenServiceDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> WebhookToken:
    """Resolve the ``Authorization: Bearer`` webhook token or raise 401."""
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Missing webhook token")
    return tokens.authenticate(credentials.credentials)


RequireToken = Annotated[WebhookToken, Depends(require_token)]


def get_admin_auth_service(db: DbSession) -> AdminAuthService:
    return AdminAuthService(db)


AdminAuthServiceDep = Annotated[AdminAuthService, Depends(get_admin_auth_service)]

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def require_trusted_origin(request: Request) -> None:
    """Refuse a state-changing request sent by a page from another origin.

    The admin cookie is ``SameSite=Strict``, but "same site" still includes
    another app on the same host and a different port (a NAS, Home Assistant and
    its apps). So a POST/DELETE carrying an ``Origin`` must come from this app's
    own origin - the ``Host`` it was sent to, or the ``X-Forwarded-Host`` a
    reverse proxy set (a cross-origin page cannot add that header without a CORS
    preflight, which the CORS middleware refuses) - or from ``cors_origins``.
    Requests without ``Origin`` (curl, the CLI, old browsers on a same-origin
    GET) are let through: no browser sends a cross-site POST without one.
    """
    if request.method in _SAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if not origin:
        return
    if origin in get_app_settings().cors_origins:
        return
    origin_host = urlsplit(origin).netloc.lower()
    own_hosts = {
        value.split(",")[0].strip().lower()
        for value in (request.headers.get("host"), request.headers.get("x-forwarded-host"))
        if value
    }
    if origin_host and origin_host in own_hosts:
        return
    logger.warning("cross-origin admin request refused", origin=origin, path=request.url.path)
    raise ForbiddenError("Cross-origin request refused")


RequireTrustedOrigin = Annotated[None, Depends(require_trusted_origin)]


def require_admin(
    request: Request, auth: AdminAuthServiceDep, _origin: RequireTrustedOrigin
) -> AdminSession:
    """Guard for ``/api/admin/*`` and ``/api/tokens``: a logged-in admin.

    In order: the structural ``ADMIN_ENABLED`` switch (403), an admin password
    must exist (403 ``ADMIN_SETUP_REQUIRED`` - never "open until someone sets
    one"), then a live session cookie (401 ``ADMIN_LOGIN_REQUIRED``).
    """
    if not get_settings().admin_enabled:
        raise ForbiddenError("Admin API is disabled (ADMIN_ENABLED=false)")
    if not auth.is_configured():
        raise AdminSetupRequiredError("Set the admin password first")
    return auth.authenticate(request.cookies.get(ADMIN_COOKIE_NAME))


RequireAdmin = Annotated[AdminSession, Depends(require_admin)]

RequireRateLimit = Annotated[None, Depends(enforce_request_rate_limit)]


def get_astrodex_handoff_service(
    db: DbSession, sessions: SessionServiceDep, storage: StorageDep
) -> AstroDexHandoffService:
    return AstroDexHandoffService(db, sessions, storage)


AstroDexHandoffServiceDep = Annotated[AstroDexHandoffService, Depends(get_astrodex_handoff_service)]


def get_stacking_service(
    db: DbSession, sessions: SessionServiceDep, storage: StorageDep
) -> StackingService:
    return StackingService(db, sessions, storage)


StackingServiceDep = Annotated[StackingService, Depends(get_stacking_service)]

# A single long-lived instance, not a fresh one per request: its cache (see
# VersionCheckService.check_for_updates) only avoids hammering GitHub if it
# actually persists across requests.
_version_check_service = VersionCheckService()


def get_version_check_service() -> VersionCheckService:
    return _version_check_service


VersionCheckServiceDep = Annotated[VersionCheckService, Depends(get_version_check_service)]
