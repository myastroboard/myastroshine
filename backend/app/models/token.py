"""Webhook token request/response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateTokenRequest(BaseModel):
    """Body of ``POST /api/tokens``."""

    name: str = Field(min_length=1, max_length=120)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class TokenOut(BaseModel):
    """A token in a listing (never includes the secret material)."""

    id: str
    name: str
    token_prefix: str
    created_at: datetime
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    revoked: bool = False


class TokenListResponse(BaseModel):
    """Body of ``GET /api/tokens``."""

    tokens: list[TokenOut]
    total: int


class CreatedTokenResponse(TokenOut):
    """Returned once by ``POST /api/tokens`` - carries the raw token.

    ``token`` is the bearer credential; ``signing_secret`` is the HMAC secret to
    configure in AstroDex. Both are shown only here.
    """

    token: str
    signing_secret: str
