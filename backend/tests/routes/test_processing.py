"""POST /api/process/{id}."""

from __future__ import annotations


def _upload(client, sample_jpeg: bytes) -> str:
    resp = client.post("/api/upload", files={"file": ("m31.jpg", sample_jpeg, "image/jpeg")})
    return resp.json()["session_id"]


def test_process_returns_completed_job(client, sample_jpeg: bytes) -> None:
    """A sync process call reports a completed job with its WS + preview URLs."""
    session_id = _upload(client, sample_jpeg)

    response = client.post(
        f"/api/process/{session_id}",
        json={"parameters": {"contrast": 1.6, "exposure": 0.2}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["status"] == "completed"
    assert body["preview_url"] == f"/api/preview/{session_id}"
    assert body["ws_status_url"] == f"/ws/processing-status/{body['job_id']}"


def test_process_changes_the_preview(client, sample_jpeg: bytes) -> None:
    """Processing with real parameters changes the served preview bytes."""
    session_id = _upload(client, sample_jpeg)
    before = client.get(f"/api/preview/{session_id}").content

    client.post(f"/api/process/{session_id}", json={"parameters": {"contrast": 2.5}})
    after = client.get(f"/api/preview/{session_id}").content

    assert before != after


def test_preview_original_is_untouched_by_processing(client, sample_jpeg: bytes) -> None:
    """``?original=true`` keeps serving the upload even after processing."""
    session_id = _upload(client, sample_jpeg)
    original = client.get(f"/api/preview/{session_id}", params={"original": "true"})
    assert original.status_code == 200
    original_bytes = original.content

    client.post(f"/api/process/{session_id}", json={"parameters": {"contrast": 2.5}})

    after_original = client.get(f"/api/preview/{session_id}", params={"original": "true"}).content
    after_full = client.get(f"/api/preview/{session_id}", params={"full": "true"}).content
    assert after_original == original_bytes
    assert after_full != original_bytes


def test_process_unknown_session_is_404(client) -> None:
    """Processing a missing session returns 404."""
    response = client.post(
        "/api/process/00000000-0000-0000-0000-000000000000",
        json={"parameters": {}},
    )
    assert response.status_code == 404


def test_process_rejects_out_of_range_parameter(client, sample_jpeg: bytes) -> None:
    """A contrast above the allowed maximum is a 400 with INVALID_PARAMETER."""
    session_id = _upload(client, sample_jpeg)

    response = client.post(
        f"/api/process/{session_id}",
        json={"parameters": {"contrast": 9.0}},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_PARAMETER"
