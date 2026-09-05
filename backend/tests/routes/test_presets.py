"""Preset routes."""

from __future__ import annotations

import cv2
import numpy as np


def _upload(client, sample_jpeg: bytes) -> str:
    resp = client.post("/api/upload", files={"file": ("m31.jpg", sample_jpeg, "image/jpeg")})
    return resp.json()["session_id"]


def _decode_shape(content: bytes) -> tuple[int, ...]:
    image = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
    assert image is not None
    return image.shape


def test_list_returns_the_five_builtins(client) -> None:
    """GET /api/presets serves the built-in presets on a fresh database."""
    response = client.get("/api/presets")

    assert response.status_code == 200
    body = response.json()
    names = {p["name"] for p in body["presets"]}
    assert {"Nebula", "Galaxy", "Deep Field", "Lunar", "Cluster"} <= names
    assert body["total"] == len(body["presets"])


def test_save_then_list_includes_new_preset(client) -> None:
    """A saved preset shows up in the list as a user preset."""
    created = client.post(
        "/api/presets",
        json={"name": "My Andromeda", "parameters": {"contrast": 1.4, "denoise": 25}},
    )
    assert created.status_code == 201
    preset_id = created.json()["preset_id"]

    listing = client.get("/api/presets").json()["presets"]
    mine = next(p for p in listing if p["preset_id"] == preset_id)
    assert mine["author"] == "user"
    assert mine["parameters"]["contrast"] == 1.4


def test_save_duplicate_name_is_400(client) -> None:
    client.post("/api/presets", json={"name": "Dup", "parameters": {}})
    again = client.post("/api/presets", json={"name": "Dup", "parameters": {}})

    assert again.status_code == 400
    assert again.json()["error_code"] == "DUPLICATE_RESOURCE"


def test_apply_preset_processes_the_session(client, sample_jpeg: bytes) -> None:
    """Applying a preset runs the pipeline and changes the preview."""
    session_id = _upload(client, sample_jpeg)
    before = client.get(f"/api/preview/{session_id}").content

    response = client.post(f"/api/presets/system_nebula/apply/{session_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert client.get(f"/api/preview/{session_id}").content != before


def test_apply_preset_keeps_the_session_crop(client, sample_jpeg: bytes) -> None:
    """A preset is a look, not a composition - applying one must not undo the
    user's crop back to the full frame."""
    session_id = _upload(client, sample_jpeg)
    client.post(
        f"/api/process/{session_id}",
        json={
            "parameters": {
                "geometry": {"crop_x": 0.25, "crop_y": 0.25, "crop_w": 0.5, "crop_h": 0.5}
            }
        },
    )
    cropped = _decode_shape(
        client.get(f"/api/preview/{session_id}", params={"full": "true"}).content
    )

    response = client.post(f"/api/presets/system_nebula/apply/{session_id}")
    assert response.status_code == 200

    after = _decode_shape(client.get(f"/api/preview/{session_id}", params={"full": "true"}).content)
    assert after == cropped  # still the cropped rectangle, not the full frame


def test_apply_unknown_preset_is_404(client, sample_jpeg: bytes) -> None:
    session_id = _upload(client, sample_jpeg)
    response = client.post(f"/api/presets/system_nope/apply/{session_id}")

    assert response.status_code == 404


def test_delete_builtin_is_403(client) -> None:
    response = client.delete("/api/presets/system_galaxy")

    assert response.status_code == 403
