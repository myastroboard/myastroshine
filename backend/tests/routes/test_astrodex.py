"""AstroDex integration routes (auth, receive, send-to-astrodex)."""

from __future__ import annotations

_CALLBACK = "http://astrodex.test/api/webhooks/enhanced-images"


def _upload(client, sample_jpeg: bytes) -> str:
    resp = client.post("/api/upload", files={"file": ("m31.jpg", sample_jpeg, "image/jpeg")})
    return resp.json()["session_id"]


def test_receive_requires_a_token(client, sample_jpeg: bytes) -> None:
    """No bearer token -> 401."""
    response = client.post(
        "/api/astrodex/receive",
        data={"image_id": "adx_1", "callback_url": _CALLBACK},
        files={"image": ("m31.jpg", sample_jpeg, "image/jpeg")},
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "UNAUTHORIZED"


def test_receive_opens_a_session(client, auth_header, sample_jpeg: bytes) -> None:
    """A valid token + image opens a session whose preview is served."""
    response = client.post(
        "/api/astrodex/receive",
        headers=auth_header,
        data={"image_id": "adx_42", "callback_url": _CALLBACK},
        files={"image": ("m31.jpg", sample_jpeg, "image/jpeg")},
    )
    assert response.status_code == 201
    session_id = response.json()["session_id"]
    assert client.get(f"/api/preview/{session_id}").status_code == 200


def test_send_to_astrodex_queues_delivery(
    client, auth_header, sample_jpeg: bytes, monkeypatch
) -> None:
    """A signed webhook is scheduled and 202 is returned immediately."""
    scheduled: list[int] = []
    monkeypatch.setattr("app.routes.astrodex.deliver_webhook", scheduled.append)
    session_id = _upload(client, sample_jpeg)

    response = client.post(
        "/api/send-to-astrodex",
        headers=auth_header,
        json={
            "session_id": session_id,
            "astrodex_image_id": "adx_42",
            "astrodex_callback_url": _CALLBACK,
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    assert len(scheduled) == 1


def test_send_to_astrodex_rejects_unlisted_callback(
    client, auth_header, sample_jpeg: bytes
) -> None:
    """A callback URL outside the allowlist is a 403."""
    session_id = _upload(client, sample_jpeg)
    response = client.post(
        "/api/send-to-astrodex",
        headers=auth_header,
        json={
            "session_id": session_id,
            "astrodex_image_id": "adx_42",
            "astrodex_callback_url": "http://evil.test/steal",
        },
    )
    assert response.status_code == 403


def test_send_to_astrodex_requires_token(client, sample_jpeg: bytes) -> None:
    session_id = _upload(client, sample_jpeg)
    response = client.post(
        "/api/send-to-astrodex",
        json={
            "session_id": session_id,
            "astrodex_image_id": "x",
            "astrodex_callback_url": _CALLBACK,
        },
    )
    assert response.status_code == 401
