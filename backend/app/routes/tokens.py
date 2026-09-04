"""Webhook token routes.

GET    /api/tokens              - list tokens (metadata only)
POST   /api/tokens              - create a token (raw value shown once)
DELETE /api/tokens/{token_id}   - revoke a token
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.dependencies import RequireAdmin, RequireRateLimit, TokenServiceDep
from app.logging_config import get_logger
from app.models import (
    CreatedTokenResponse,
    CreateTokenRequest,
    TokenListResponse,
    TokenOut,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/tokens", tags=["tokens"])


@router.get("", response_model=TokenListResponse)
async def list_tokens(
    tokens: TokenServiceDep, _admin: RequireAdmin, _rate_limit: RequireRateLimit
) -> TokenListResponse:
    """List every token with its metadata (never the secret)."""
    records = tokens.list_tokens()
    return TokenListResponse(
        tokens=[TokenOut.model_validate(record, from_attributes=True) for record in records],
        total=len(records),
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CreatedTokenResponse)
async def create_token(
    request: CreateTokenRequest,
    tokens: TokenServiceDep,
    _admin: RequireAdmin,
    _rate_limit: RequireRateLimit,
) -> CreatedTokenResponse:
    """Create a long-lived token. The ``token`` and ``signing_secret`` are
    returned only in this response - store them now."""
    record, raw = tokens.create_token(request.name, request.expires_in_days)
    return CreatedTokenResponse(
        **TokenOut.model_validate(record, from_attributes=True).model_dump(),
        token=raw,
        signing_secret=record.signing_secret,
    )


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(
    token_id: str, tokens: TokenServiceDep, _admin: RequireAdmin, _rate_limit: RequireRateLimit
) -> None:
    """Revoke a token immediately."""
    tokens.revoke_token(token_id)
