"""FastAPI dependency wiring.

Routes depend on these annotated types; nothing here contains business logic.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.image_processing import ImageProcessingService
from app.services.session import SessionService
from app.services.storage import StorageService

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
