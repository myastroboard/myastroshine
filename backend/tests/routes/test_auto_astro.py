"""Auto Astro route."""

from __future__ import annotations


def _upload(client, sample_jpeg: bytes) -> str:
    resp = client.post("/api/upload", files={"file": ("m31.jpg", sample_jpeg, "image/jpeg")})
    return resp.json()["session_id"]


def test_apply_dispatches_processing_and_returns_parameters(client, sample_jpeg: bytes) -> None:
    session_id = _upload(client, sample_jpeg)

    response = client.post(f"/api/auto-astro/{session_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["status"] == "completed"
    assert "job_id" in body
    assert "parameters" in body
    assert 0.5 <= body["parameters"]["contrast"] <= 3.0


def test_apply_unknown_session_is_404(client) -> None:
    response = client.post("/api/auto-astro/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
