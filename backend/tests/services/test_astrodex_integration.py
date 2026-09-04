"""AstroDexService: HMAC signing and webhook delivery with retries."""

from __future__ import annotations

import json

import httpx
import pytest

from app.services.astrodex_integration import (
    AstroDexService,
    canonical_json,
    generate_signature,
    verify_signature,
)

_PAYLOAD = {"event": "image_enhanced", "data": {"b": 2, "a": 1}}


def test_canonical_json_is_sorted_and_compact() -> None:
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_signature_roundtrip() -> None:
    """A payload signed by generate_signature verifies with verify_signature."""
    header = generate_signature(_PAYLOAD, "secret")
    assert header.startswith("sha256=")
    assert verify_signature(json.dumps(_PAYLOAD), header, "secret")


def test_verify_rejects_tampered_payload() -> None:
    header = generate_signature(_PAYLOAD, "secret")
    tampered = json.dumps({**_PAYLOAD, "data": {"a": 1, "b": 3}})
    assert not verify_signature(tampered, header, "secret")


def test_verify_rejects_wrong_secret() -> None:
    header = generate_signature(_PAYLOAD, "secret")
    assert not verify_signature(json.dumps(_PAYLOAD), header, "other")


@pytest.mark.asyncio
async def test_send_webhook_success_signs_request() -> None:
    """A 200 stops after one attempt and the request carries the signature."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json={"ok": True})

    service = AstroDexService(transport=httpx.MockTransport(handler))
    result = await service.send_webhook("https://astrodex.test/hook", _PAYLOAD, "secret")

    assert result == {"success": True, "attempts": 1, "status_code": 200}
    assert seen["x-webhook-signature"] == generate_signature(_PAYLOAD, "secret")


@pytest.mark.asyncio
async def test_send_webhook_retries_transient_then_succeeds() -> None:
    """503 twice, then 200 -> success on the third attempt."""
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200) if calls["n"] >= 3 else httpx.Response(503)

    service = AstroDexService(transport=httpx.MockTransport(handler))
    result = await service.send_webhook("https://astrodex.test/hook", _PAYLOAD, "secret")

    assert result["success"] is True
    assert result["attempts"] == 3


@pytest.mark.asyncio
async def test_send_webhook_gives_up_after_max_retries() -> None:
    """Persistent 503 exhausts the retries and reports failure."""
    service = AstroDexService(transport=httpx.MockTransport(lambda _r: httpx.Response(503)))
    result = await service.send_webhook("https://astrodex.test/hook", _PAYLOAD, "secret")

    assert result["success"] is False
    assert result["attempts"] == 3


@pytest.mark.asyncio
async def test_send_webhook_does_not_retry_client_error() -> None:
    """A 400 is terminal - no retries."""
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400)

    service = AstroDexService(transport=httpx.MockTransport(handler))
    result = await service.send_webhook("https://astrodex.test/hook", _PAYLOAD, "secret")

    assert result["success"] is False
    assert calls["n"] == 1
