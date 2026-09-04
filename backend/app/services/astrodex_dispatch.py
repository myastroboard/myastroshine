"""AstroDexDispatch - orchestrates the two AstroDex flows.

Inbound  : receive an image + callback details, open a session.
Outbound : queue a signed ``image_enhanced`` webhook, delivered in the
           background with retries (:func:`deliver_webhook`).
"""

from __future__ import annotations

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import database
from app.db.models import AstroDexLink, SessionRecord, WebhookToken
from app.exceptions import ForbiddenError
from app.logging_config import get_logger
from app.services.astrodex_integration import AstroDexService
from app.services.session import SessionService
from app.services.storage import StorageService
from app.utils import image_utils
from app.utils.app_settings import load_or_generate_secret_key
from app.utils.validators import is_allowed_callback_url

logger = get_logger(__name__)


def _check_callback_url(url: str) -> None:
    if not is_allowed_callback_url(url):
        raise ForbiddenError(f"Callback URL {url} is not on the allowlist")


class AstroDexDispatch:
    """Request-scoped orchestration for the AstroDex integration."""

    def __init__(self, db: Session, sessions: SessionService, storage: StorageService) -> None:
        self.db = db
        self.sessions = sessions
        self.storage = storage

    def _link_for(self, session_id: str) -> AstroDexLink | None:
        return self.db.scalar(select(AstroDexLink).where(AstroDexLink.session_id == session_id))

    def receive_image(
        self,
        *,
        token: WebhookToken,
        astrodex_image_id: str,
        image: np.ndarray,
        callback_url: str,
        callback_token: str | None,
    ) -> AstroDexLink:
        """Open a session for an AstroDex-pushed image and record the callback."""
        _check_callback_url(callback_url)
        record = self.sessions.create_session(image_path="", original_filename=astrodex_image_id)
        self.storage.save_original(record.session_id, image)
        record.image_path = str(self.storage.original_path(record.session_id))

        link = AstroDexLink(
            session_id=record.session_id,
            astrodex_image_id=astrodex_image_id,
            callback_url=callback_url,
            callback_token=callback_token or token.id,
            webhook_status="received",
        )
        self.db.add(link)
        self.db.commit()
        self.db.refresh(link)
        logger.info(
            "astrodex image received",
            session_id=record.session_id,
            image_id=astrodex_image_id,
        )
        return link

    def queue_send(
        self,
        *,
        session_id: str,
        astrodex_image_id: str,
        callback_url: str,
        signing_token: WebhookToken,
    ) -> AstroDexLink:
        """Create or refresh the link and mark it pending delivery."""
        self.sessions.get_session(session_id)
        _check_callback_url(callback_url)

        link = self._link_for(session_id) or AstroDexLink(session_id=session_id)
        link.astrodex_image_id = astrodex_image_id
        link.callback_url = callback_url
        link.callback_token = signing_token.id
        link.webhook_status = "pending"
        link.webhook_error = None
        self.db.add(link)
        self.db.commit()
        self.db.refresh(link)
        return link


async def run_delivery(db: Session, link_id: int, astrodex: AstroDexService) -> None:
    """Build, sign, POST the webhook, and update the link row. Testable core."""
    link = db.get(AstroDexLink, link_id)
    if link is None:
        logger.error("run_delivery: link missing", link_id=link_id)
        return

    token = db.get(WebhookToken, link.callback_token) if link.callback_token else None
    secret = token.signing_secret if token else load_or_generate_secret_key()
    session = db.get(SessionRecord, link.session_id)

    try:
        image = StorageService().load_processed(link.session_id)
        height, width = image.shape[:2]
        payload = astrodex.build_payload(
            original_image_id=link.astrodex_image_id,
            image_bytes=image_utils.encode_image(image, "jpeg", 92),
            image_format="jpeg",
            width=width,
            height=height,
            session_id=link.session_id,
            parameters=session.parameters if session and session.parameters else {},
            preview_url=f"/api/preview/{link.session_id}?full=true",
        )
        result = await astrodex.send_webhook(link.callback_url, payload, secret)
    except OSError as exc:
        link.webhook_status = "failed"
        link.webhook_error = str(exc)
        db.commit()
        logger.exception("run_delivery: could not build payload", link_id=link_id)
        return

    link.webhook_status = "sent" if result["success"] else "failed"
    link.webhook_error = (
        None if result["success"] else f"delivery failed after {result['attempts']} attempt(s)"
    )
    db.commit()
    logger.info("webhook delivered", link_id=link_id, status=link.webhook_status)


async def deliver_webhook(link_id: int) -> None:
    """Background-task entry point: opens its own DB session."""
    with database.SessionLocal() as db:
        await run_delivery(db, link_id, AstroDexService())
