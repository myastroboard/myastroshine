"""AstroDex handoff crypto - the shared HMAC contract with MyAstroBoard.

MyAstroBoard mints a signed *handoff token* when a user sends an AstroDex
picture here for enhancement; this instance verifies it, pulls the source image,
and later POSTs the enhanced result back with its own signature. Both sides
implement the primitives below identically (see ``docs/API.md`` and
``initial_plan/PASSATION_MYASTROBOARD_INTEGRATION.md``).

- Handoff token: ``b64url(payload_json).b64url(HMAC_SHA256(b64url(payload_json)))``
  - the MAC is over the base64url payload *string*, and the signature segment is
  the raw digest base64url-encoded (not hex). base64url carries no ``=`` padding.
- Enhanced-upload signature: ``sha256=<hex>`` over
  ``canonical_json(payload) + "\n" + sha256_hex(image_bytes)`` - the hex form the
  existing webhook convention uses, extended to cover the multipart image body.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time

from app.exceptions import UnauthorizedError
from app.types import JsonDict


def canonical_json(payload: JsonDict) -> str:
    """Deterministic JSON string used as a signing input (sorted keys, no space)."""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    try:
        return base64.urlsafe_b64decode(segment + padding)
    except (binascii.Error, ValueError) as exc:
        raise UnauthorizedError("Malformed handoff token") from exc


def sign_handoff(payload: JsonDict, secret: str) -> str:
    """Build a handoff token for ``payload`` (used in tests; the board mints the
    real ones)."""
    payload_segment = _b64url_encode(canonical_json(payload).encode("utf-8"))
    digest = hmac.new(secret.encode("utf-8"), payload_segment.encode("ascii"), hashlib.sha256)
    return f"{payload_segment}.{_b64url_encode(digest.digest())}"


def decode_handoff_claims(token: str) -> JsonDict:
    """Read a handoff token's claims **without** verifying the signature.

    Only for the two fields needed to *find* the verification key and target:
    ``kid`` (which webhook token signed it) and ``callback_base``. Never trust
    anything else from the result before :func:`verify_handoff` has passed.
    """
    payload_segment, _, signature_segment = token.partition(".")
    if not payload_segment or not signature_segment:
        raise UnauthorizedError("Malformed handoff token")
    try:
        claims = json.loads(_b64url_decode(payload_segment))
    except (json.JSONDecodeError, ValueError) as exc:
        raise UnauthorizedError("Malformed handoff token") from exc
    if not isinstance(claims, dict):
        raise UnauthorizedError("Malformed handoff token")
    return claims


def verify_handoff(token: str, secret: str) -> JsonDict:
    """Return the token's claims if the signature and expiry check out, else raise."""
    payload_segment, _, signature_segment = token.partition(".")
    if not payload_segment or not signature_segment:
        raise UnauthorizedError("Malformed handoff token")

    expected = hmac.new(
        secret.encode("utf-8"), payload_segment.encode("ascii"), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(expected, _b64url_decode(signature_segment)):
        raise UnauthorizedError("Invalid handoff signature")

    claims = decode_handoff_claims(token)
    expires_at = claims.get("exp")
    if not isinstance(expires_at, int | float) or expires_at < time.time():
        raise UnauthorizedError("Handoff token has expired")
    return claims


def enhanced_signing_input(payload: JsonDict, image_bytes: bytes) -> str:
    """The exact string HMAC'd for the enhanced-image upload back to AstroDex."""
    return canonical_json(payload) + "\n" + hashlib.sha256(image_bytes).hexdigest()


def sign_enhanced_upload(payload: JsonDict, image_bytes: bytes, secret: str) -> str:
    """``sha256=<hex>`` for ``POST /api/astrodex/integration/enhanced``."""
    digest = hmac.new(
        secret.encode("utf-8"),
        enhanced_signing_input(payload, image_bytes).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"
