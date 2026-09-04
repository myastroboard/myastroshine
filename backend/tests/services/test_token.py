"""TokenService: creation, listing, revocation, authentication."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.exceptions import ResourceNotFoundError, UnauthorizedError
from app.services.token import TokenService


def test_create_returns_raw_once_and_stores_only_hash(db_session) -> None:
    """The raw token is returned but never persisted in cleartext."""
    service = TokenService(db_session)
    record, raw = service.create_token("astrodex-prod")

    assert raw.startswith("mas_")
    assert record.token_hash != raw
    assert record.token_prefix == raw[:12]
    assert record.signing_secret and record.signing_secret != raw


def test_authenticate_accepts_valid_token(db_session) -> None:
    service = TokenService(db_session)
    record, raw = service.create_token("t")

    authed = service.authenticate(raw)
    assert authed.id == record.id
    assert authed.last_used_at is not None


def test_authenticate_rejects_unknown_token(db_session) -> None:
    with pytest.raises(UnauthorizedError):
        TokenService(db_session).authenticate("mas_not-a-real-token")


def test_authenticate_rejects_revoked(db_session) -> None:
    service = TokenService(db_session)
    record, raw = service.create_token("t")
    service.revoke_token(record.id)

    with pytest.raises(UnauthorizedError, match="revoked"):
        service.authenticate(raw)


def test_authenticate_rejects_expired(db_session) -> None:
    service = TokenService(db_session)
    record, raw = service.create_token("t", expires_in_days=1)
    record.expires_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.commit()

    with pytest.raises(UnauthorizedError, match="expired"):
        service.authenticate(raw)


def test_revoke_unknown_raises(db_session) -> None:
    with pytest.raises(ResourceNotFoundError):
        TokenService(db_session).revoke_token("nope")


def test_list_is_newest_first(db_session) -> None:
    service = TokenService(db_session)
    service.create_token("first")
    service.create_token("second")

    names = [t.name for t in service.list_tokens()]
    assert names == ["second", "first"]
