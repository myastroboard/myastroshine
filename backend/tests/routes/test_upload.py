"""POST /api/upload and GET /api/preview/{id}."""

from __future__ import annotations

import cv2
import numpy as np


def _upload(client, sample_jpeg: bytes):
    return client.post(
        "/api/upload",
        files={"file": ("m31.jpg", sample_jpeg, "image/jpeg")},
    )


def _decode(content: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
    assert image is not None
    return image


def test_upload_opens_a_session(client, sample_jpeg: bytes) -> None:
    """A valid JPEG returns a session id, dimensions, and a histogram."""
    response = _upload(client, sample_jpeg)

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"]
    assert body["dimensions"] == {"width": 96, "height": 64}
    assert body["file_size_bytes"] == len(sample_jpeg)
    assert len(body["histogram"]["r"]) == 256
    assert body["image_url"] == f"/api/preview/{body['session_id']}"


def test_upload_rejects_non_image(client) -> None:
    """Bytes that are not an image get 415 with the error envelope."""
    response = client.post(
        "/api/upload",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["error_code"] == "UNSUPPORTED_FORMAT"


def test_upload_rejects_unsupported_extension(client, sample_jpeg: bytes) -> None:
    """A .bmp filename is rejected before decoding."""
    response = client.post(
        "/api/upload",
        files={"file": ("photo.bmp", sample_jpeg, "image/bmp")},
    )

    assert response.status_code == 415


def test_preview_returns_jpeg(client, sample_jpeg: bytes) -> None:
    """The preview endpoint serves a JPEG for a live session."""
    session_id = _upload(client, sample_jpeg).json()["session_id"]

    preview = client.get(f"/api/preview/{session_id}")
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/jpeg"
    assert preview.content[:2] == b"\xff\xd8"

    full = client.get(f"/api/preview/{session_id}", params={"full": "true"})
    assert full.status_code == 200


def test_preview_unknown_session_is_404(client) -> None:
    """An unknown session id returns 404 with SESSION_NOT_FOUND."""
    response = client.get("/api/preview/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["error_code"] == "SESSION_NOT_FOUND"


def test_preview_original_with_geometry_matches_the_cropped_result(
    client, sample_jpeg: bytes
) -> None:
    """After a crop, original+geometry stays frame-aligned with the result (the
    before/after comparison depends on this - see docs/API.md)."""
    session_id = _upload(client, sample_jpeg).json()["session_id"]
    process = client.post(
        f"/api/process/{session_id}",
        json={
            "parameters": {
                "geometry": {"crop_x": 0.25, "crop_y": 0.25, "crop_w": 0.5, "crop_h": 0.5}
            }
        },
    )
    assert process.status_code == 200

    original_geo = client.get(
        f"/api/preview/{session_id}", params={"original": "true", "geometry": "true"}
    )
    full = client.get(f"/api/preview/{session_id}", params={"full": "true"})
    assert original_geo.status_code == 200
    assert original_geo.headers["content-type"] == "image/jpeg"
    assert _decode(original_geo.content).shape == _decode(full.content).shape


def test_preview_original_without_geometry_stays_the_untouched_upload(
    client, sample_jpeg: bytes
) -> None:
    """Plain ``original=true`` (no ``geometry``) always serves the raw upload,
    crop or not - the CropTool depends on this to offer the full frame."""
    session_id = _upload(client, sample_jpeg).json()["session_id"]
    client.post(
        f"/api/process/{session_id}",
        json={
            "parameters": {
                "geometry": {"crop_x": 0.25, "crop_y": 0.25, "crop_w": 0.5, "crop_h": 0.5}
            }
        },
    )

    original = client.get(f"/api/preview/{session_id}", params={"original": "true"})
    assert _decode(original.content).shape[:2] == (64, 96)


def test_preview_original_with_geometry_falls_back_before_any_processing(
    client, sample_jpeg: bytes
) -> None:
    """No parameters saved yet - degrades to the plain untouched original."""
    session_id = _upload(client, sample_jpeg).json()["session_id"]

    response = client.get(
        f"/api/preview/{session_id}", params={"original": "true", "geometry": "true"}
    )
    assert response.status_code == 200
    assert _decode(response.content).shape[:2] == (64, 96)
