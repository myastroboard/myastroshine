"""GET /api/looks/{id}/thumbnail - the "Style" gallery thumbnails."""

from __future__ import annotations

import cv2
import numpy as np


def _upload(client, sample_jpeg: bytes) -> str:
    resp = client.post("/api/upload", files={"file": ("m31.jpg", sample_jpeg, "image/jpeg")})
    return resp.json()["session_id"]


def _decode(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    assert image is not None
    return image


def test_thumbnail_before_any_render_uses_the_preview(client, sample_jpeg: bytes) -> None:
    """A fresh upload has no pre-look render yet: the thumbnail comes from its preview."""
    session_id = _upload(client, sample_jpeg)

    plain = client.get(f"/api/looks/{session_id}/thumbnail")
    styled = client.get(f"/api/looks/{session_id}/thumbnail", params={"look": "soft_glow"})

    assert plain.status_code == 200
    assert plain.headers["content-type"] == "image/jpeg"
    assert styled.status_code == 200
    assert not np.array_equal(_decode(plain.content), _decode(styled.content))


def test_thumbnail_uses_the_pre_look_render(client, sample_jpeg: bytes) -> None:
    """After a render with a look, the no-look thumbnail shows the edit without it."""
    session_id = _upload(client, sample_jpeg)
    client.post(f"/api/process/{session_id}", json={"parameters": {"contrast": 1.5}})
    before = _decode(client.get(f"/api/looks/{session_id}/thumbnail").content)

    client.post(
        f"/api/process/{session_id}",
        json={"parameters": {"contrast": 1.5, "look": {"look_id": "vivid", "amount": 90}}},
    )
    after = _decode(client.get(f"/api/looks/{session_id}/thumbnail").content)

    assert np.array_equal(before, after)


def test_thumbnail_amount_zero_is_the_plain_thumbnail(client, sample_jpeg: bytes) -> None:
    session_id = _upload(client, sample_jpeg)
    plain = client.get(f"/api/looks/{session_id}/thumbnail")
    zero = client.get(
        f"/api/looks/{session_id}/thumbnail", params={"look": "cinematic", "amount": 0}
    )
    assert plain.content == zero.content


def test_thumbnail_rejects_an_unknown_look_or_amount(client, sample_jpeg: bytes) -> None:
    session_id = _upload(client, sample_jpeg)
    bad_look = client.get(f"/api/looks/{session_id}/thumbnail", params={"look": "spikes"})
    bad_amount = client.get(
        f"/api/looks/{session_id}/thumbnail", params={"look": "vivid", "amount": 101}
    )
    assert bad_look.status_code == 400
    assert bad_amount.status_code == 400


def test_thumbnail_unknown_session_is_404(client) -> None:
    response = client.get("/api/looks/00000000-0000-0000-0000-000000000000/thumbnail")
    assert response.status_code == 404


def test_thumbnail_invalid_session_id_is_404(client) -> None:
    response = client.get("/api/looks/not-a-session/thumbnail")
    assert response.status_code == 404
