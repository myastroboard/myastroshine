"""SessionService - create, load, and expire processing sessions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SessionRecord
from app.exceptions import SessionExpiredError, SessionNotFoundError
from app.logging_config import get_logger
from app.services.storage import StorageService
from app.types import JsonDict
from app.utils.app_settings import get_app_settings

logger = get_logger(__name__)


class SessionService:
    """CRUD and lifecycle for :class:`app.db.models.SessionRecord`."""

    def __init__(self, db: Session, storage: StorageService | None = None) -> None:
        self.db = db
        self.storage = storage or StorageService()

    def create_session(
        self, image_path: str, original_filename: str | None = None
    ) -> SessionRecord:
        """Persist a new session and return the row."""
        now = datetime.now(UTC)
        record = SessionRecord(
            session_id=str(uuid.uuid4()),
            image_path=image_path,
            original_filename=original_filename,
            created_at=now,
            expires_at=now + timedelta(hours=get_app_settings().session_expiry_hours),
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        logger.info("session created", session_id=record.session_id)
        return record

    def get_session(self, session_id: str) -> SessionRecord:
        """Load a live session, raising if it is missing or expired."""
        record = self.db.get(SessionRecord, session_id)
        if record is None:
            raise SessionNotFoundError(f"Session {session_id} not found")
        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < datetime.now(UTC):
            raise SessionExpiredError(f"Session {session_id} has expired")
        return record

    def update_parameters(self, session_id: str, parameters: JsonDict) -> None:
        """Store the last-applied parameters for a session."""
        record = self.get_session(session_id)
        record.parameters = parameters
        self.db.commit()

    def cleanup_old_sessions(self) -> int:
        """Delete expired session rows and their files. Returns the count removed."""
        now = datetime.now(UTC)
        expired = self.db.scalars(select(SessionRecord).where(SessionRecord.expires_at < now)).all()
        for record in expired:
            self.storage.delete_session(record.session_id)
            self.db.delete(record)
        self.db.commit()
        if expired:
            logger.info("expired sessions cleaned", count=len(expired))
        return len(expired)
