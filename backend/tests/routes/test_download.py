"""POST /api/download/{id}."""

from __future__ import annotations


def _upload(client, sample_jpeg: bytes) -> str:
    resp = client.post("/api/upload", files={"file": ("m31.jpg", sample_jpeg, "image/jpeg")})
    return resp.json()["session_id"]


def test_download_returns_attachment(client, sample_jpeg: bytes) -> None:
    """Download serves the processed image as a JPEG attachment."""
    session_id = _upload(client, sample_jpeg)

    response = client.post(f"/api/download/{session_id}", json={"format": "jpeg", "quality": 90})

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert "attachment" in response.headers["content-disposition"]
    assert response.content[:2] == b"\xff\xd8"


def test_download_png(client, sample_jpeg: bytes) -> None:
    """PNG is an accepted output format."""
    session_id = _upload(client, sample_jpeg)

    response = client.post(f"/api/download/{session_id}", json={"format": "png"})

    assert response.status_code == 200
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_download_unknown_session_is_404(client) -> None:
    response = client.post(
        "/api/download/00000000-0000-0000-0000-000000000000",
        json={},
    )
    assert response.status_code == 404


def test_download_rejects_bad_format(client, sample_jpeg: bytes) -> None:
    """An unsupported format string fails request validation (400)."""
    session_id = _upload(client, sample_jpeg)

    response = client.post(f"/api/download/{session_id}", json={"format": "gif"})

    assert response.status_code == 400
