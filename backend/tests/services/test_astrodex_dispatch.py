"""AstroDexDispatch orchestration and background delivery."""

from __future__ import annotations

import httpx
import numpy as np
import pytest

from app.exceptions import ForbiddenError
from app.services.astrodex_dispatch import AstroDexDispatch, run_delivery
from app.services.astrodex_integration import AstroDexService
from app.services.session import SessionService
from app.services.storage import StorageService
from app.services.token import TokenService
from app.utils.app_settings import save_app_settings

_CALLBACK = "http://astrodex.test/api/webhooks/enhanced-images"


@pytest.fixture
def dispatch(db_session) -> AstroDexDispatch:
    # No explicit root: uses images_dir under the test DATA_DIR, which is what
    # the background job's own StorageService() will read too.
    storage = StorageService()
    return AstroDexDispatch(db_session, SessionService(db_session, storage), storage)


def test_receive_image_creates_session_and_link(
    dispatch: AstroDexDispatch, db_session, sample_image: np.ndarray
) -> None:
    token, _ = TokenService(db_session).create_token("t")
    link = dispatch.receive_image(
        token=token,
        astrodex_image_id="adx_1",
        image=sample_image,
        callback_url=_CALLBACK,
        callback_token=None,
    )
    assert link.webhook_status == "received"
    assert link.callback_token == token.id
    assert dispatch.storage.has_session(link.session_id)


def test_queue_send_rejects_unlisted_url(
    dispatch: AstroDexDispatch, db_session, sample_image: np.ndarray
) -> None:
    token, _ = TokenService(db_session).create_token("t")
    session_id = dispatch.sessions.create_session(image_path="").session_id
    dispatch.storage.save_original(session_id, sample_image)

    with pytest.raises(ForbiddenError):
        dispatch.queue_send(
            session_id=session_id,
            astrodex_image_id="x",
            callback_url="http://evil.test/x",
            signing_token=token,
        )


def test_queue_send_rejects_everything_when_allowlist_empty(
    dispatch: AstroDexDispatch, db_session, sample_image: np.ndarray
) -> None:
    """An empty allowlist fails closed - it used to allow any callback URL."""
    save_app_settings({"astrodex_callback_urls": []})
    token, _ = TokenService(db_session).create_token("t")
    session_id = dispatch.sessions.create_session(image_path="").session_id
    dispatch.storage.save_original(session_id, sample_image)

    with pytest.raises(ForbiddenError):
        dispatch.queue_send(
            session_id=session_id,
            astrodex_image_id="x",
            callback_url=_CALLBACK,  # would have matched a non-empty allowlist
            signing_token=token,
        )


@pytest.mark.asyncio
async def test_run_delivery_signs_and_marks_sent(
    dispatch: AstroDexDispatch, db_session, sample_image: np.ndarray
) -> None:
    """run_delivery posts the webhook and flips the link to 'sent'."""
    token, _ = TokenService(db_session).create_token("t")
    session_id = dispatch.sessions.create_session(image_path="").session_id
    dispatch.storage.save_original(session_id, sample_image)
    link = dispatch.queue_send(
        session_id=session_id,
        astrodex_image_id="adx_9",
        callback_url=_CALLBACK,
        signing_token=token,
    )

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["signature"] = request.headers.get("x-webhook-signature")
        captured["body"] = request.content
        return httpx.Response(200)

    await run_delivery(db_session, link.id, AstroDexService(transport=httpx.MockTransport(handler)))

    db_session.refresh(link)
    assert link.webhook_status == "sent"
    assert str(captured["signature"]).startswith("sha256=")


@pytest.mark.asyncio
async def test_run_delivery_marks_failed_on_persistent_error(
    dispatch: AstroDexDispatch, db_session, sample_image: np.ndarray
) -> None:
    token, _ = TokenService(db_session).create_token("t")
    session_id = dispatch.sessions.create_session(image_path="").session_id
    dispatch.storage.save_original(session_id, sample_image)
    link = dispatch.queue_send(
        session_id=session_id,
        astrodex_image_id="adx_9",
        callback_url=_CALLBACK,
        signing_token=token,
    )

    await run_delivery(
        db_session,
        link.id,
        AstroDexService(transport=httpx.MockTransport(lambda _r: httpx.Response(503))),
    )

    db_session.refresh(link)
    assert link.webhook_status == "failed"
    assert link.webhook_error is not None
