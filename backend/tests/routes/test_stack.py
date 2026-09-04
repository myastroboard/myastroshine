"""Stacking routes: initiate -> upload-frame -> process -> get."""

from __future__ import annotations

import numpy as np

from tests.support import png_bytes, translate


def test_full_stack_workflow(client, star_field: np.ndarray) -> None:
    """initiate, upload 3 frames, process, then read the result back."""
    init = client.post(
        "/api/stack/initiate",
        json={"frame_count": 3, "combination_method": "median"},
    )
    assert init.status_code == 202
    stack_id = init.json()["stack_id"]

    status = ""
    for i in range(3):
        frame = png_bytes(translate(star_field, i, -i))
        up = client.post(
            f"/api/stack/{stack_id}/upload-frame",
            data={"frame_index": str(i)},
            files={"file": (f"f{i}.png", frame, "image/png")},
        )
        assert up.status_code == 202
        status = up.json()["status"]
    assert status == "ready"

    processed = client.post(f"/api/stack/{stack_id}/process")
    assert processed.status_code == 200
    body = processed.json()
    assert body["status"] == "completed"
    assert body["session_id"]
    assert body["statistics"]["frames_stacked"] == 3

    # the composite is a real session, enhanceable and previewable
    assert client.get(body["stacked_image_url"].replace("?full=true", "")).status_code == 200

    fetched = client.get(f"/api/stack/{stack_id}")
    assert fetched.json()["status"] == "completed"


def test_initiate_rejects_too_few_frames(client) -> None:
    assert client.post("/api/stack/initiate", json={"frame_count": 1}).status_code == 400


def test_upload_frame_unknown_stack_is_404(client, star_field: np.ndarray) -> None:
    response = client.post(
        "/api/stack/nope/upload-frame",
        data={"frame_index": "0"},
        files={"file": ("f.png", png_bytes(star_field), "image/png")},
    )
    assert response.status_code == 404


def test_get_unknown_stack_is_404(client) -> None:
    assert client.get("/api/stack/nope").status_code == 404
