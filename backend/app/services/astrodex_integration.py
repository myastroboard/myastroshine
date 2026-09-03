"""AstroDexService - webhook integration with AstroDex (MyAstroBoard).

Contract and payload shapes live in docs/API.md and the planning docs.
Authentication is HMAC-SHA256 over the canonical JSON payload.
"""

from __future__ import annotations

from app.logging_config import get_logger
from app.types import JsonDict

logger = get_logger(__name__)


class AstroDexService:
    """Sends enhanced images back to AstroDex and validates inbound requests."""

    def generate_signature(self, payload: JsonDict, secret: str) -> str:
        """Return ``sha256=<hexdigest>`` for the canonical JSON of ``payload``."""
        raise NotImplementedError

    def verify_signature(self, raw_payload: str, signature_header: str, secret: str) -> bool:
        """Constant-time check of an inbound webhook signature."""
        raise NotImplementedError

    async def receive_image(
        self,
        image_id: str,
        image_bytes: bytes,
        metadata: JsonDict,
        callback_url: str,
        callback_token: str,
    ) -> JsonDict:
        """Validate, store an AstroDex-pushed image, and open a session."""
        raise NotImplementedError

    async def send_webhook(self, callback_url: str, payload: JsonDict, secret: str) -> JsonDict:
        """POST a signed webhook with exponential-backoff retries."""
        raise NotImplementedError
