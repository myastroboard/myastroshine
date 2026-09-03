"""AstroDexService tests. Filled in during Sprint 4."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="AstroDexService not implemented yet (Sprint 4)")


def test_signature_roundtrip() -> None:
    """A payload signed by generate_signature verifies with verify_signature."""


def test_verify_signature_rejects_tampered_payload() -> None:
    """Changing one byte of the payload fails verification."""


def test_send_webhook_retries_with_backoff() -> None:
    """A 503 response triggers retries with exponential backoff, then gives up."""
