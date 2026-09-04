"""FastAPI dependency wiring.

Routes depend on these annotated types; nothing here contains business logic.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.database import get_db
from app.db.models import WebhookToken
from app.exceptions import ForbiddenError, UnauthorizedError
from app.services.astrodex_dispatch import AstroDexDispatch
from app.services.astrodex_integration import AstroDexService
from app.services.depth_map import DepthMapService
from app.services.depth_shift import DepthShiftService
from app.services.enhancement import EnhancementService
from app.services.image_processing import ImageProcessingService
from app.services.job import JobService
from app.services.preset import PresetService
from app.services.session import SessionService
from app.services.stacking import StackingService
from app.services.storage import StorageService
from app.services.token import TokenService
from app.utils.rate_limit import enforce_request_rate_limit

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


EnhancementServiceDep = Annotated[EnhancementService, Depends(get_enhancement_service)]
PresetServiceDep = Annotated[PresetService, Depends(get_preset_service)]
DepthShiftServiceDep = Annotated[DepthShiftService, Depends(get_depth_shift_service)]


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


def require_admin() -> None:
    """Guard for ``/api/admin/*`` writes. Off means the endpoint 403s."""
    if not get_settings().admin_enabled:
        raise ForbiddenError("Admin API is disabled (ADMIN_ENABLED=false)")


RequireAdmin = Annotated[None, Depends(require_admin)]

RequireRateLimit = Annotated[None, Depends(enforce_request_rate_limit)]


def get_astrodex_service() -> AstroDexService:
    return AstroDexService()


def get_astrodex_dispatch(
    db: DbSession, sessions: SessionServiceDep, storage: StorageDep
) -> AstroDexDispatch:
    return AstroDexDispatch(db, sessions, storage)


AstroDexServiceDep = Annotated[AstroDexService, Depends(get_astrodex_service)]
AstroDexDispatchDep = Annotated[AstroDexDispatch, Depends(get_astrodex_dispatch)]


def get_stacking_service(
    db: DbSession, sessions: SessionServiceDep, storage: StorageDep
) -> StackingService:
    return StackingService(db, sessions, storage)


StackingServiceDep = Annotated[StackingService, Depends(get_stacking_service)]
