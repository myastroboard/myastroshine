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


def test_download_malformed_session_id_is_404(client) -> None:
    """A syntactically invalid id is rejected before ever hitting storage."""
    response = client.post("/api/download/not-a-valid-id", json={})
    assert response.status_code == 404


def test_download_rejects_bad_format(client, sample_jpeg: bytes) -> None:
    """An unsupported format string fails request validation (400)."""
    session_id = _upload(client, sample_jpeg)

    response = client.post(f"/api/download/{session_id}", json={"format": "gif"})

    assert response.status_code == 400


def _process_with_look(client, session_id: str) -> None:
    client.post(
        f"/api/process/{session_id}",
        json={"parameters": {"contrast": 1.3, "look": {"look_id": "vivid", "amount": 70}}},
    )


def test_download_with_a_look_names_it_in_the_metadata(client, sample_jpeg: bytes) -> None:
    """With a look active, the default download carries it and says so."""
    session_id = _upload(client, sample_jpeg)
    _process_with_look(client, session_id)

    jpeg = client.post(f"/api/download/{session_id}", json={"format": "jpeg"})
    png = client.post(f"/api/download/{session_id}", json={"format": "png"})

    assert jpeg.status_code == 200
    assert b"MyAstroShine style: vivid (70%)" in jpeg.content
    assert b"MyAstroShine style: vivid (70%)" in png.content


def test_download_without_the_style_returns_the_plain_edit(client, sample_jpeg: bytes) -> None:
    """``style: false`` exports the same edit without its look, and no style metadata."""
    session_id = _upload(client, sample_jpeg)
    _process_with_look(client, session_id)

    styled = client.post(f"/api/download/{session_id}", json={"format": "png"})
    plain = client.post(f"/api/download/{session_id}", json={"format": "png", "style": False})

    assert plain.status_code == 200
    assert b"MyAstroShine style" not in plain.content
    assert plain.content != styled.content


def test_download_without_a_look_has_no_style_metadata(client, sample_jpeg: bytes) -> None:
    session_id = _upload(client, sample_jpeg)
    client.post(f"/api/process/{session_id}", json={"parameters": {"contrast": 1.3}})

    response = client.post(f"/api/download/{session_id}", json={"format": "jpeg", "style": False})

    assert response.status_code == 200
    assert b"MyAstroShine style" not in response.content
