"""TokenService - long-lived bearer tokens for the AstroDex integration.

Tokens are created and revoked from the UI. The raw value is returned once and
never stored; only its SHA-256 hash is kept for constant-time lookup.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import WebhookToken
from app.exceptions import ResourceNotFoundError, UnauthorizedError
from app.logging_config import get_logger

logger = get_logger(__name__)

_TOKEN_PREFIX = "mas_"  # noqa: S105 - label prefix, not a secret


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TokenService:
    """CRUD and authentication for :class:`app.db.models.WebhookToken`."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_token(
        self, name: str, expires_in_days: int | None = None
    ) -> tuple[WebhookToken, str]:
        """Create a token; returns ``(record, raw_token)``. The raw token is
        shown to the caller once and cannot be recovered later."""
        raw = _TOKEN_PREFIX + secrets.token_urlsafe(32)
        expires_at = (
            datetime.now(UTC) + timedelta(days=expires_in_days)
            if expires_in_days is not None
            else None
        )
        record = WebhookToken(
            id=str(uuid.uuid4()),
            name=name,
            token_prefix=raw[: len(_TOKEN_PREFIX) + 8],
            token_hash=_hash(raw),
            signing_secret=secrets.token_hex(32),
            expires_at=expires_at,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        logger.info("webhook token created", token_id=record.id, name=name)
        return record, raw

    def list_tokens(self) -> list[WebhookToken]:
        return list(
            self.db.scalars(select(WebhookToken).order_by(WebhookToken.created_at.desc())).all()
        )

    def revoke_token(self, token_id: str) -> None:
        record = self.db.get(WebhookToken, token_id)
        if record is None:
            raise ResourceNotFoundError(f"Token {token_id} not found")
        record.revoked = True
        self.db.commit()
        logger.info("webhook token revoked", token_id=token_id)

    def authenticate(self, raw_token: str) -> WebhookToken:
        """Resolve a bearer token, or raise :class:`UnauthorizedError`."""
        record = self.db.scalar(
            select(WebhookToken).where(WebhookToken.token_hash == _hash(raw_token))
        )
        if record is None or not hmac.compare_digest(record.token_hash, _hash(raw_token)):
            raise UnauthorizedError("Invalid webhook token")
        if record.revoked:
            raise UnauthorizedError("Webhook token has been revoked")
        expires_at = record.expires_at
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at < datetime.now(UTC):
                raise UnauthorizedError("Webhook token has expired")

        record.last_used_at = datetime.now(UTC)
        self.db.commit()
        return record
