"""AstroDexHandoffService - the two halves of the MyAstroBoard handoff.

``resume``  : verify a signed handoff token, pull the source image + metadata
              from MyAstroBoard, and open an editing session for it.
``return_enhanced`` : sign the enhanced result and POST it back to the board,
              which files it as a new (duplicated) picture on the same object.

Only ever calls *out* to MyAstroBoard (the board never needs to reach this
instance), so the whole flow works whether the board is on the LAN or behind a
public reverse proxy. See ``docs/API.md`` and
``initial_plan/PASSATION_MYASTROBOARD_INTEGRATION.md``.
"""

from __future__ import annotations

import asyncio

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import __version__
from app.db.models import AstroDexLink, SessionRecord, WebhookToken
from app.exceptions import ForbiddenError, ResourceNotFoundError, UnauthorizedError, UpstreamError
from app.logging_config import get_logger
from app.services.astrodex_integration import (
    canonical_json,
    decode_handoff_claims,
    sign_enhanced_upload,
    verify_handoff,
)
from app.services.session import SessionService
from app.services.storage import StorageService
from app.types import JsonDict
from app.utils import image_utils
from app.utils.app_settings import get_app_settings
from app.utils.validators import is_allowed_callback_url

logger = get_logger(__name__)

_RETRYABLE_STATUS = {500, 502, 503, 504}
_PULL_TIMEOUT_SECONDS = 30.0
_RETURN_TIMEOUT_SECONDS = 30.0


def _dig(data: object, *keys: str) -> str | None:
    """Best-effort ``data[k1][k2]...`` as a string, or ``None``."""
    node = data
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node if isinstance(node, str) and node else None


class AstroDexHandoffService:
    """Request-scoped orchestration for the AstroDex <-> editor handoff."""

    def __init__(
        self,
        db: Session,
        sessions: SessionService,
        storage: StorageService,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.db = db
        self.sessions = sessions
        self.storage = storage
        self._transport = transport

    # -- inbound: board -> editor -----------------------------------------

    async def resume(self, handoff: str) -> tuple[SessionRecord, AstroDexLink]:
        """Verify ``handoff``, fetch the source image, and open a session."""
        claims = decode_handoff_claims(handoff)
        kid = str(claims.get("kid") or "")
        callback_base = str(claims.get("callback_base") or "").rstrip("/")

        verify_handoff(handoff, self._signing_secret(kid))

        if not callback_base or not is_allowed_callback_url(callback_base):
            raise ForbiddenError(
                f"Handoff callback {callback_base!r} is not on the astrodex_callback_urls allowlist"
            )

        item_id = str(claims.get("item_id") or "")
        picture_id = str(claims.get("picture_id") or "")
        if not item_id or not picture_id:
            raise UnauthorizedError("Handoff token is missing the picture reference")

        meta, image_bytes = await self._pull_source(callback_base, handoff)
        object_name = _dig(meta, "object", "name")
        source_filename = _dig(meta, "image", "filename")

        image = image_utils.decode_image(image_bytes, source_filename)
        record = self.sessions.create_session(
            image_path="", original_filename=object_name or source_filename
        )
        self.storage.save_original(record.session_id, image)
        record.image_path = str(self.storage.original_path(record.session_id))

        link = AstroDexLink(
            session_id=record.session_id,
            callback_base=callback_base,
            handoff_token=handoff,
            astrodex_item_id=item_id,
            astrodex_picture_id=picture_id,
            object_name=object_name,
            webhook_status="received",
        )
        self.db.add(link)
        self.db.commit()
        self.db.refresh(record)
        logger.info(
            "astrodex handoff resumed",
            session_id=record.session_id,
            item_id=item_id,
            picture_id=picture_id,
        )
        return record, link

    async def _pull_source(self, callback_base: str, handoff: str) -> tuple[JsonDict, bytes]:
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=_PULL_TIMEOUT_SECONDS
            ) as client:
                meta_response = await client.get(
                    f"{callback_base}/api/astrodex/integration/source",
                    params={"handoff": handoff},
                )
                meta_response.raise_for_status()
                meta = meta_response.json()
                # The board hands back a relative image URL with the handoff
                # already in it; fall back to the canonical path if it is absent.
                image_path = _dig(meta, "image", "url") or (
                    f"/api/astrodex/integration/source/image?handoff={handoff}"
                )
                image_response = await client.get(f"{callback_base}{image_path}")
                image_response.raise_for_status()
                image_bytes = image_response.content
        except httpx.HTTPStatusError as exc:
            logger.warning("astrodex source rejected", status=exc.response.status_code)
            raise UpstreamError(
                f"AstroDex rejected the handoff ({exc.response.status_code})"
            ) from exc
        except (httpx.RequestError, ValueError) as exc:
            logger.warning("astrodex source unreachable", error=str(exc))
            raise UpstreamError("Could not reach AstroDex to fetch the source image") from exc

        if not isinstance(meta, dict) or not image_bytes:
            raise UpstreamError("AstroDex returned an unusable source response")
        return meta, image_bytes

    # -- outbound: editor -> board --------------------------------------

    async def return_enhanced(self, session_id: str) -> AstroDexLink:
        """Sign and POST the enhanced result back to AstroDex."""
        self.sessions.get_session(session_id)  # 404 / 410 if the session is gone

        link = self.db.scalar(select(AstroDexLink).where(AstroDexLink.session_id == session_id))
        if link is None:
            raise ResourceNotFoundError("This session was not opened from AstroDex")

        session = self.db.get(SessionRecord, session_id)
        payload: JsonDict = {
            "parameters": session.parameters if session and session.parameters else {},
            "myastroshine_version": __version__,
        }
        image_bytes = image_utils.encode_image(self.storage.load_processed(session_id), "jpeg", 92)
        secret = self._signing_secret(
            str(decode_handoff_claims(link.handoff_token).get("kid") or "")
        )
        signature = sign_enhanced_upload(payload, image_bytes, secret)

        link.webhook_status = "pending"
        link.webhook_error = None
        self.db.commit()

        try:
            await self._post_enhanced(link, payload, image_bytes, signature)
        except UpstreamError as exc:
            link.webhook_status = "failed"
            link.webhook_error = str(exc)
            self.db.commit()
            raise

        link.webhook_status = "sent"
        link.webhook_error = None
        self.db.commit()
        self.db.refresh(link)
        logger.info("enhanced image returned to astrodex", session_id=session_id, link_id=link.id)
        return link

    async def _post_enhanced(
        self, link: AstroDexLink, payload: JsonDict, image_bytes: bytes, signature: str
    ) -> None:
        settings = get_app_settings()
        url = f"{link.callback_base}/api/astrodex/integration/enhanced"
        headers = {
            "X-Webhook-Signature": signature,
            "X-Webhook-Signature-Algorithm": "HMAC-SHA256",
        }
        # The 'payload' form field is the exact canonical JSON the signature is
        # computed over, so the board can verify it against the raw bytes.
        form = {"handoff": link.handoff_token, "payload": canonical_json(payload)}
        files = {"image": ("enhanced.jpg", image_bytes, "image/jpeg")}

        last_error = "delivery failed"
        for attempt in range(1, settings.astrodex_max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    transport=self._transport, timeout=_RETURN_TIMEOUT_SECONDS
                ) as client:
                    response = await client.post(url, data=form, files=files, headers=headers)
            except httpx.RequestError as exc:
                last_error = f"could not reach AstroDex ({exc.__class__.__name__})"
                logger.warning("enhanced return request error", attempt=attempt, error=str(exc))
            else:
                if response.is_success:
                    return
                # 409 == the board already consumed this handoff: a previous
                # attempt landed even though its response did not reach us.
                if response.status_code == httpx.codes.CONFLICT:
                    logger.info("enhanced image already delivered (handoff consumed)")
                    return
                if response.status_code not in _RETRYABLE_STATUS:
                    raise UpstreamError(
                        f"AstroDex rejected the enhanced image ({response.status_code})"
                    )
                last_error = f"AstroDex returned {response.status_code}"
                logger.warning(
                    "enhanced return transient failure", attempt=attempt, error=last_error
                )

            if attempt < settings.astrodex_max_retries:
                await asyncio.sleep(settings.astrodex_retry_delay_seconds * (2 ** (attempt - 1)))

        raise UpstreamError(last_error)

    # -- helpers -------------------------------------------------------

    def _signing_secret(self, kid: str) -> str:
        """The ``signing_secret`` of the webhook token whose prefix is ``kid``."""
        if not kid:
            raise UnauthorizedError("Handoff token has no key id")
        record = self.db.scalar(
            select(WebhookToken).where(
                WebhookToken.token_prefix == kid, WebhookToken.revoked.is_(False)
            )
        )
        if record is None:
            raise UnauthorizedError("Handoff token was signed by an unknown or revoked key")
        return record.signing_secret
