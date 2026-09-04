"""AstroDexService - signed webhook delivery to AstroDex (MyAstroBoard).

Outbound webhooks are HMAC-SHA256 signed over the canonical JSON of the payload
(sorted keys, no whitespace). Delivery retries with exponential backoff.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime

import httpx

from app.logging_config import get_logger
from app.types import JsonDict
from app.utils.app_settings import get_app_settings

logger = get_logger(__name__)

_RETRYABLE_STATUS = {500, 502, 503, 504}


def canonical_json(payload: JsonDict) -> str:
    """Deterministic JSON string used as the signing input."""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def generate_signature(payload: JsonDict, secret: str) -> str:
    """Return ``sha256=<hexdigest>`` for the canonical JSON of ``payload``."""
    digest = hmac.new(
        secret.encode("utf-8"), canonical_json(payload).encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"sha256={digest}"


def verify_signature(raw_payload: str, signature_header: str, secret: str) -> bool:
    """Constant-time check of an inbound webhook signature."""
    expected = generate_signature(json.loads(raw_payload), secret)
    return hmac.compare_digest(expected, signature_header)


class AstroDexService:
    """Builds and delivers the ``image_enhanced`` webhook."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    def build_payload(
        self,
        *,
        original_image_id: str,
        image_bytes: bytes,
        image_format: str,
        width: int,
        height: int,
        session_id: str,
        parameters: JsonDict,
        preview_url: str,
    ) -> JsonDict:
        """Assemble the webhook body (see docs/API.md)."""
        return {
            "event": "image_enhanced",
            "source": "MyAstroShine",
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {
                "original_image_id": original_image_id,
                "enhanced_image": {
                    "blob": base64.b64encode(image_bytes).decode("ascii"),
                    "format": image_format,
                    "width": width,
                    "height": height,
                    "file_size_bytes": len(image_bytes),
                },
                "processing_metadata": {
                    "session_id": session_id,
                    "parameters": parameters,
                },
                "preview_url": preview_url,
            },
        }

    async def send_webhook(self, callback_url: str, payload: JsonDict, secret: str) -> JsonDict:
        """POST a signed webhook, retrying transient failures with backoff.

        Returns ``{"success": bool, "attempts": int, "status_code": int | None}``.
        """
        signature = generate_signature(payload, secret)
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Webhook-Signature-Algorithm": "HMAC-SHA256",
        }
        app_settings = get_app_settings()
        base_delay = app_settings.astrodex_retry_delay_seconds
        max_attempts = app_settings.astrodex_max_retries

        async with httpx.AsyncClient(transport=self._transport, timeout=10.0) as client:
            for attempt in range(1, max_attempts + 1):
                try:
                    response = await client.post(
                        callback_url, content=canonical_json(payload), headers=headers
                    )
                except httpx.RequestError as exc:
                    logger.warning("webhook request error", attempt=attempt, error=str(exc))
                else:
                    if response.is_success:
                        return {
                            "success": True,
                            "attempts": attempt,
                            "status_code": response.status_code,
                        }
                    if response.status_code not in _RETRYABLE_STATUS:
                        logger.error(
                            "webhook rejected", status=response.status_code, attempt=attempt
                        )
                        return {
                            "success": False,
                            "attempts": attempt,
                            "status_code": response.status_code,
                        }
                    logger.warning(
                        "webhook transient failure", status=response.status_code, attempt=attempt
                    )

                if attempt < max_attempts:
                    await asyncio.sleep(base_delay * (2 ** (attempt - 1)))

        logger.error("webhook delivery failed", url=callback_url, attempts=max_attempts)
        return {"success": False, "attempts": max_attempts, "status_code": None}
