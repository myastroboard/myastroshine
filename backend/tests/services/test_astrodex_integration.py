"""The shared HMAC contract with MyAstroBoard: handoff tokens and the
enhanced-upload signature."""

from __future__ import annotations

import time

import pytest

from app.exceptions import UnauthorizedError
from app.services.astrodex_integration import (
    _b64url_decode,
    _b64url_encode,
    canonical_json,
    decode_handoff_claims,
    enhanced_signing_input,
    sign_enhanced_upload,
    sign_handoff,
    verify_handoff,
)

_SECRET = "s" * 64


def _claims(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "kid": "mas_1wZcTkdO",
        "callback_base": "https://astro.example.test",
        "item_id": "item-1",
        "picture_id": "pic-1",
        "user_id": "user-1",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "jti": "abc123",
    }
    base.update(overrides)
    return base


def test_canonical_json_is_sorted_and_compact() -> None:
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_handoff_round_trip_returns_the_claims() -> None:
    """A token from sign_handoff verifies and yields the original claims."""
    claims = _claims()
    token = sign_handoff(claims, _SECRET)

    verified = verify_handoff(token, _SECRET)

    assert verified["item_id"] == "item-1"
    assert verified["callback_base"] == "https://astro.example.test"


def test_verify_handoff_rejects_a_wrong_secret() -> None:
    token = sign_handoff(_claims(), _SECRET)
    with pytest.raises(UnauthorizedError, match="signature"):
        verify_handoff(token, "x" * 64)


def test_verify_handoff_rejects_a_tampered_payload() -> None:
    token = sign_handoff(_claims(), _SECRET)
    payload_segment, _, signature_segment = token.partition(".")
    forged = sign_handoff(_claims(item_id="other"), _SECRET).partition(".")[0]
    with pytest.raises(UnauthorizedError):
        verify_handoff(f"{forged}.{signature_segment}", _SECRET)
    assert payload_segment  # (sanity: the original had a payload segment)


def test_verify_handoff_rejects_an_expired_token() -> None:
    token = sign_handoff(_claims(exp=int(time.time()) - 1), _SECRET)
    with pytest.raises(UnauthorizedError, match="expired"):
        verify_handoff(token, _SECRET)


def test_verify_handoff_rejects_a_malformed_token() -> None:
    with pytest.raises(UnauthorizedError, match="Malformed"):
        verify_handoff("not-a-token", _SECRET)


def test_decode_claims_does_not_verify_but_reads_routing_fields() -> None:
    """decode_handoff_claims exposes kid/callback_base before the key is known."""
    token = sign_handoff(_claims(), "some-other-secret")
    claims = decode_handoff_claims(token)
    assert claims["kid"] == "mas_1wZcTkdO"
    assert claims["callback_base"] == "https://astro.example.test"


def test_decode_claims_rejects_a_token_with_no_separator() -> None:
    with pytest.raises(UnauthorizedError, match="Malformed"):
        decode_handoff_claims("no-dot-here")


def test_decode_claims_rejects_a_payload_that_is_not_valid_json() -> None:
    bad_payload = _b64url_encode(b"not json {")
    with pytest.raises(UnauthorizedError, match="Malformed"):
        decode_handoff_claims(f"{bad_payload}.sig")


def test_decode_claims_rejects_a_payload_that_is_not_a_json_object() -> None:
    array_payload = _b64url_encode(b"[1, 2, 3]")
    with pytest.raises(UnauthorizedError, match="Malformed"):
        decode_handoff_claims(f"{array_payload}.sig")


def test_b64url_decode_rejects_invalid_base64() -> None:
    with pytest.raises(UnauthorizedError, match="Malformed"):
        _b64url_decode("!!!not-base64!!!")


def test_enhanced_signature_is_hex_and_covers_the_image() -> None:
    payload = {"parameters": {"contrast": 1.2}, "myastroshine_version": "0.3.0"}
    header = sign_enhanced_upload(payload, b"image-bytes", _SECRET)
    assert header.startswith("sha256=")
    # A different image body changes the signature.
    other = sign_enhanced_upload(payload, b"other-bytes", _SECRET)
    assert other != header


def test_enhanced_signing_input_is_stable_across_payload_key_order() -> None:
    a = enhanced_signing_input({"a": 1, "b": 2}, b"x")
    b = enhanced_signing_input({"b": 2, "a": 1}, b"x")
    assert a == b
