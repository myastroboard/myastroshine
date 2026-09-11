"""AstroDexHandoffService: verify + pull on resume, sign + POST on return."""

from __future__ import annotations

import time

import httpx
import pytest
from sqlalchemy import select

from app.db.models import AstroDexLink
from app.exceptions import (
    ForbiddenError,
    ResourceNotFoundError,
    UnauthorizedError,
    UpstreamError,
)
from app.services.astrodex_handoff import AstroDexHandoffService, _dig
from app.services.astrodex_integration import sign_handoff
from app.services.session import SessionService
from app.services.storage import StorageService
from app.utils.app_settings import save_app_settings

_CALLBACK_BASE = "http://astrodex.test"


@pytest.fixture(autouse=True)
def _allow_callback() -> None:
    save_app_settings(
        {"astrodex_callback_urls": [_CALLBACK_BASE], "astrodex_retry_delay_seconds": 0}
    )


def _handoff(kid: str, secret: str, **overrides: object) -> str:
    claims: dict[str, object] = {
        "kid": kid,
        "callback_base": _CALLBACK_BASE,
        "item_id": "item-1",
        "picture_id": "pic-1",
        "user_id": "user-1",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "jti": "jti-1",
    }
    claims.update(overrides)
    return sign_handoff(claims, secret)


def _service(db_session: object, transport: httpx.MockTransport) -> AstroDexHandoffService:
    storage = StorageService()
    return AstroDexHandoffService(
        db_session, SessionService(db_session, storage), storage, transport=transport
    )


def _source_transport(jpeg: bytes) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        handoff = request.url.params.get("handoff")
        if request.url.path.endswith("/integration/source"):
            return httpx.Response(
                200,
                json={
                    "object": {"item_id": "item-1", "name": "M31 - Andromeda Galaxy"},
                    "picture": {"source_picture_id": "pic-1", "notes": "first light"},
                    "image": {
                        "url": f"/api/astrodex/integration/source/image?handoff={handoff}",
                        "filename": "m31.jpg",
                        "content_type": "image/jpeg",
                    },
                },
            )
        if request.url.path.endswith("/integration/source/image"):
            return httpx.Response(200, content=jpeg, headers={"content-type": "image/jpeg"})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


async def test_resume_verifies_pulls_and_opens_a_session(
    db_session, webhook_token, sample_jpeg: bytes
) -> None:
    """A valid handoff opens a session with the pulled image and an AstroDexLink."""
    record, raw = webhook_token
    service = _service(db_session, _source_transport(sample_jpeg))

    session, link = await service.resume(_handoff(raw[:12], record.signing_secret))

    assert service.storage.has_session(session.session_id)
    assert link.astrodex_item_id == "item-1"
    assert link.astrodex_picture_id == "pic-1"
    assert link.object_name == "M31 - Andromeda Galaxy"
    assert link.webhook_status == "received"


async def test_resume_rejects_a_handoff_signed_with_the_wrong_secret(
    db_session, webhook_token, sample_jpeg: bytes
) -> None:
    _, raw = webhook_token
    service = _service(db_session, _source_transport(sample_jpeg))
    with pytest.raises(UnauthorizedError):
        await service.resume(_handoff(raw[:12], "not-the-secret"))


async def test_resume_rejects_an_unknown_key_id(db_session, sample_jpeg: bytes) -> None:
    service = _service(db_session, _source_transport(sample_jpeg))
    with pytest.raises(UnauthorizedError, match="unknown or revoked"):
        await service.resume(_handoff("mas_deadbeef", "whatever"))


async def test_resume_rejects_a_callback_base_off_the_allowlist(
    db_session, webhook_token, sample_jpeg: bytes
) -> None:
    record, raw = webhook_token
    service = _service(db_session, _source_transport(sample_jpeg))
    token = _handoff(raw[:12], record.signing_secret, callback_base="http://evil.test")
    with pytest.raises(ForbiddenError):
        await service.resume(token)


async def test_resume_surfaces_an_upstream_failure(db_session, webhook_token) -> None:
    record, raw = webhook_token
    service = _service(db_session, httpx.MockTransport(lambda _r: httpx.Response(500)))
    with pytest.raises(UpstreamError):
        await service.resume(_handoff(raw[:12], record.signing_secret))


async def test_return_enhanced_signs_and_marks_sent(
    db_session, webhook_token, sample_jpeg: bytes
) -> None:
    record, raw = webhook_token
    service = _service(db_session, _source_transport(sample_jpeg))
    session, _ = await service.resume(_handoff(raw[:12], record.signing_secret))

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["signature"] = request.headers.get("x-webhook-signature")
        captured["body"] = request.content
        return httpx.Response(201, json={"status": "created", "picture_id": "pic-2"})

    service._transport = httpx.MockTransport(handler)
    result = await service.return_enhanced(session.session_id)

    assert result.webhook_status == "sent"
    assert str(captured["signature"]).startswith("sha256=")
    assert b"enhanced.jpg" in bytes(captured["body"])  # the multipart image part


async def test_return_enhanced_marks_failed_on_persistent_error(
    db_session, webhook_token, sample_jpeg: bytes
) -> None:
    record, raw = webhook_token
    service = _service(db_session, _source_transport(sample_jpeg))
    session, _ = await service.resume(_handoff(raw[:12], record.signing_secret))

    service._transport = httpx.MockTransport(lambda _r: httpx.Response(503))
    with pytest.raises(UpstreamError):
        await service.return_enhanced(session.session_id)

    db_session.expire_all()
    link = db_session.scalar(
        select(AstroDexLink).where(AstroDexLink.session_id == session.session_id)
    )
    assert link.webhook_status == "failed"
    assert link.webhook_error is not None


async def test_return_enhanced_treats_conflict_as_already_delivered(
    db_session, webhook_token, sample_jpeg: bytes
) -> None:
    record, raw = webhook_token
    service = _service(db_session, _source_transport(sample_jpeg))
    session, _ = await service.resume(_handoff(raw[:12], record.signing_secret))

    service._transport = httpx.MockTransport(lambda _r: httpx.Response(409))
    result = await service.return_enhanced(session.session_id)
    assert result.webhook_status == "sent"


async def test_return_enhanced_without_a_link_is_not_found(
    db_session, webhook_token, sample_image
) -> None:
    """A session with no AstroDexLink cannot be returned to AstroDex."""
    storage = StorageService()
    sessions = SessionService(db_session, storage)
    record = sessions.create_session(image_path="")
    storage.save_original(record.session_id, sample_image)

    service = _service(db_session, httpx.MockTransport(lambda _r: httpx.Response(200)))
    with pytest.raises(ResourceNotFoundError):
        await service.return_enhanced(record.session_id)


def test_dig_stops_at_the_first_non_dict_node() -> None:
    assert _dig({"object": "not-a-dict"}, "object", "name") is None
    assert _dig({"a": {"b": "value"}}, "a", "b") == "value"
    assert _dig({"a": {"b": ""}}, "a", "b") is None  # empty string is not truthy


async def test_resume_rejects_a_handoff_missing_the_picture_reference(
    db_session, webhook_token
) -> None:
    record, raw = webhook_token
    service = _service(db_session, httpx.MockTransport(lambda _r: httpx.Response(404)))
    token = _handoff(raw[:12], record.signing_secret, item_id="", picture_id="")
    with pytest.raises(UnauthorizedError, match="missing the picture reference"):
        await service.resume(token)


async def test_resume_rejects_a_handoff_with_no_key_id(db_session) -> None:
    service = _service(db_session, httpx.MockTransport(lambda _r: httpx.Response(404)))
    token = _handoff("", "whatever-secret")
    with pytest.raises(UnauthorizedError, match="no key id"):
        await service.resume(token)


async def test_resume_surfaces_a_network_error_reaching_astrodex(db_session, webhook_token) -> None:
    record, raw = webhook_token

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    service = _service(db_session, httpx.MockTransport(handler))
    with pytest.raises(UpstreamError, match="Could not reach AstroDex"):
        await service.resume(_handoff(raw[:12], record.signing_secret))


async def test_resume_rejects_an_unusable_source_response(db_session, webhook_token) -> None:
    """The source endpoint returns 200 but with no usable image bytes."""
    record, raw = webhook_token

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/integration/source"):
            return httpx.Response(200, json={"object": {}, "image": {"filename": "x.jpg"}})
        return httpx.Response(200, content=b"")  # empty image body

    service = _service(db_session, httpx.MockTransport(handler))
    with pytest.raises(UpstreamError, match="unusable source response"):
        await service.resume(_handoff(raw[:12], record.signing_secret))


async def test_return_enhanced_retries_past_a_network_error_then_succeeds(
    db_session, webhook_token, sample_jpeg: bytes
) -> None:
    record, raw = webhook_token
    service = _service(db_session, _source_transport(sample_jpeg))
    session, _ = await service.resume(_handoff(raw[:12], record.signing_secret))

    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise httpx.ConnectError("connection reset")
        return httpx.Response(201, json={"status": "created"})

    service._transport = httpx.MockTransport(handler)
    result = await service.return_enhanced(session.session_id)

    assert result.webhook_status == "sent"
    assert attempts["n"] == 2


async def test_return_enhanced_stops_retrying_on_a_non_retryable_status(
    db_session, webhook_token, sample_jpeg: bytes
) -> None:
    """A 400 (bad request, not a transient server error) fails immediately
    instead of burning through every retry attempt."""
    record, raw = webhook_token
    service = _service(db_session, _source_transport(sample_jpeg))
    session, _ = await service.resume(_handoff(raw[:12], record.signing_secret))

    attempts = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(400, json={"error": "malformed payload"})

    service._transport = httpx.MockTransport(handler)
    with pytest.raises(UpstreamError, match="rejected the enhanced image"):
        await service.return_enhanced(session.session_id)

    assert attempts["n"] == 1  # no retries for a non-transient rejection
