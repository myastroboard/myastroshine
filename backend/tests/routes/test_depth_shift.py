"""Depth shift routes."""

from __future__ import annotations


def _upload(client, sample_jpeg: bytes) -> str:
    resp = client.post("/api/upload", files={"file": ("m31.jpg", sample_jpeg, "image/jpeg")})
    return resp.json()["session_id"]


def test_generate_returns_layers_and_stats(client, sample_jpeg: bytes) -> None:
    """POST /depth-shift/{id} builds N layers and returns their URLs + stats."""
    session_id = _upload(client, sample_jpeg)

    response = client.post(f"/api/depth-shift/{session_id}", json={"num_layers": 5})

    assert response.status_code == 200
    body = response.json()
    assert body["num_layers"] == 5
    assert len(body["depth_layers"]) == 5
    assert body["depth_layers"][0]["depth_range"] == [0.0, 0.2]
    assert body["statistics"]["max_depth"] <= 255


def test_layer_and_depth_map_are_png(client, sample_jpeg: bytes) -> None:
    """The layer and depth-map endpoints serve PNGs after generation."""
    session_id = _upload(client, sample_jpeg)
    client.post(f"/api/depth-shift/{session_id}", json={})

    layer = client.get(f"/api/depth-shift/{session_id}/layer_0")
    assert layer.status_code == 200
    assert layer.headers["content-type"] == "image/png"
    assert layer.content[:8] == b"\x89PNG\r\n\x1a\n"

    depth = client.get(f"/api/depth-shift/{session_id}/depth_map")
    assert depth.status_code == 200
    assert depth.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_metadata_reports_generation_state(client, sample_jpeg: bytes) -> None:
    session_id = _upload(client, sample_jpeg)

    before = client.get(f"/api/depth-shift/{session_id}/metadata").json()
    assert before["depth_map_generated"] is False

    client.post(f"/api/depth-shift/{session_id}", json={"num_layers": 4})
    after = client.get(f"/api/depth-shift/{session_id}/metadata").json()
    assert after["depth_map_generated"] is True
    assert len(after["layer_urls"]) == 4


def test_layer_before_generation_is_404(client, sample_jpeg: bytes) -> None:
    session_id = _upload(client, sample_jpeg)
    response = client.get(f"/api/depth-shift/{session_id}/layer_0")
    assert response.status_code == 404


def test_generate_unknown_session_is_404(client) -> None:
    response = client.post("/api/depth-shift/00000000-0000-0000-0000-000000000000", json={})
    assert response.status_code == 404


def test_num_layers_out_of_range_is_400(client, sample_jpeg: bytes) -> None:
    session_id = _upload(client, sample_jpeg)
    response = client.post(f"/api/depth-shift/{session_id}", json={"num_layers": 99})
    assert response.status_code == 400


def test_generate_accepts_a_focus_point(client, sample_jpeg: bytes) -> None:
    session_id = _upload(client, sample_jpeg)
    response = client.post(
        f"/api/depth-shift/{session_id}",
        json={"num_layers": 4, "focus_point": {"x": 0.2, "y": 0.8}},
    )
    assert response.status_code == 200
    assert response.json()["num_layers"] == 4
