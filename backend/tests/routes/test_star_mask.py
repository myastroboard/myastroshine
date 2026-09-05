"""Star mask preview route."""

from __future__ import annotations


def _upload(client, sample_jpeg: bytes) -> str:
    resp = client.post("/api/upload", files={"file": ("m31.jpg", sample_jpeg, "image/jpeg")})
    return resp.json()["session_id"]


def test_detect_returns_source_count_and_fractional_positions(client, sample_jpeg: bytes) -> None:
    session_id = _upload(client, sample_jpeg)

    response = client.post(f"/api/star-mask/{session_id}", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["source_count"] == len(body["stars"])
    for star in body["stars"]:
        assert 0.0 <= star["x"] <= 1.0
        assert 0.0 <= star["y"] <= 1.0
        assert 0.0 <= star["radius"] <= 1.0


def test_detect_accepts_custom_sensitivity_and_max_size(client, sample_jpeg: bytes) -> None:
    session_id = _upload(client, sample_jpeg)

    response = client.post(f"/api/star-mask/{session_id}", json={"sensitivity": 90, "max_size": 10})

    assert response.status_code == 200


def test_detect_unknown_session_is_404(client) -> None:
    response = client.post("/api/star-mask/00000000-0000-0000-0000-000000000000", json={})
    assert response.status_code == 404


def test_detect_out_of_range_sensitivity_is_400(client, sample_jpeg: bytes) -> None:
    session_id = _upload(client, sample_jpeg)
    response = client.post(f"/api/star-mask/{session_id}", json={"sensitivity": 500})
    assert response.status_code == 400
