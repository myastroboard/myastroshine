"""AstroDex handoff routes: resume opens a session, return delivers the result."""

from __future__ import annotations

import time
from collections.abc import Iterator

import httpx
import pytest

from app.db.database import get_db
from app.dependencies import get_astrodex_handoff_service
from app.main import app
from app.services.astrodex_handoff import AstroDexHandoffService
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


@pytest.fixture
def mock_board(client, sample_jpeg: bytes) -> Iterator[dict[str, object]]:
    """Override the handoff service with one whose HTTP calls hit a mock board."""
    state: dict[str, object] = {"enhanced_status": 201, "enhanced_requests": []}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/integration/source"):
            handoff = request.url.params.get("handoff")
            return httpx.Response(
                200,
                json={
                    "object": {"item_id": "item-1", "name": "M31"},
                    "picture": {"source_picture_id": "pic-1"},
                    "image": {
                        "url": f"/api/astrodex/integration/source/image?handoff={handoff}",
                        "filename": "m31.jpg",
                        "content_type": "image/jpeg",
                    },
                },
            )
        if path.endswith("/integration/source/image"):
            return httpx.Response(200, content=sample_jpeg, headers={"content-type": "image/jpeg"})
        if path.endswith("/integration/enhanced"):
            state["enhanced_requests"].append(bytes(request.content))  # type: ignore[union-attr]
            return httpx.Response(int(state["enhanced_status"]), json={"status": "created"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    def override_service() -> AstroDexHandoffService:
        db = next(app.dependency_overrides[get_db]())
        storage = StorageService()
        return AstroDexHandoffService(db, SessionService(db, storage), storage, transport=transport)

    app.dependency_overrides[get_astrodex_handoff_service] = override_service
    try:
        yield state
    finally:
        app.dependency_overrides.pop(get_astrodex_handoff_service, None)


def _handoff(raw_token: str, secret: str, **overrides: object) -> str:
    claims: dict[str, object] = {
        "kid": raw_token[:12],
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


def test_resume_opens_a_session_from_a_signed_handoff(client, webhook_token, mock_board) -> None:
    record, raw = webhook_token
    response = client.post(
        "/api/astrodex/handoff/resume", json={"handoff": _handoff(raw, record.signing_secret)}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["object_name"] == "M31"
    assert body["astrodex_item_id"] == "item-1"
    assert client.get(f"/api/preview/{body['session_id']}").status_code == 200


def test_resume_rejects_a_bad_signature(client, webhook_token, mock_board) -> None:
    _, raw = webhook_token
    response = client.post(
        "/api/astrodex/handoff/resume", json={"handoff": _handoff(raw, "wrong-secret")}
    )
    assert response.status_code == 401


def test_resume_rejects_an_expired_handoff(client, webhook_token, mock_board) -> None:
    record, raw = webhook_token
    token = _handoff(raw, record.signing_secret, exp=int(time.time()) - 5)
    response = client.post("/api/astrodex/handoff/resume", json={"handoff": token})
    assert response.status_code == 401


def test_return_delivers_the_enhanced_image(client, webhook_token, mock_board) -> None:
    record, raw = webhook_token
    session_id = client.post(
        "/api/astrodex/handoff/resume", json={"handoff": _handoff(raw, record.signing_secret)}
    ).json()["session_id"]

    response = client.post("/api/astrodex/handoff/return", json={"session_id": session_id})

    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    assert len(mock_board["enhanced_requests"]) == 1  # type: ignore[arg-type]


def test_return_reports_a_delivery_failure(client, webhook_token, mock_board) -> None:
    record, raw = webhook_token
    mock_board["enhanced_status"] = 503
    session_id = client.post(
        "/api/astrodex/handoff/resume", json={"handoff": _handoff(raw, record.signing_secret)}
    ).json()["session_id"]

    response = client.post("/api/astrodex/handoff/return", json={"session_id": session_id})
    assert response.status_code == 502


def test_return_on_a_plain_session_is_404(client, sample_jpeg: bytes, mock_board) -> None:
    session_id = client.post(
        "/api/upload", files={"file": ("m.jpg", sample_jpeg, "image/jpeg")}
    ).json()["session_id"]
    response = client.post("/api/astrodex/handoff/return", json={"session_id": session_id})
    assert response.status_code == 404
