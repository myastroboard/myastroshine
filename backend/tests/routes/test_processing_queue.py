"""Queue-mode processing: Celery runs eagerly in tests.

With ``PROCESSING_MODE=queue`` the route enqueues ``task_process_image``. Because
``APP_ENV=test`` puts Celery in eager mode, the task runs inline, so the job is
already ``completed`` by the time we read it back.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _queue_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PROCESSING_MODE", "queue")
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _upload(client, sample_jpeg: bytes) -> str:
    return client.post(
        "/api/upload", files={"file": ("m31.jpg", sample_jpeg, "image/jpeg")}
    ).json()["session_id"]


def test_process_enqueues_and_eager_task_completes(client, sample_jpeg: bytes) -> None:
    session_id = _upload(client, sample_jpeg)

    response = client.post(f"/api/process/{session_id}", json={"parameters": {"contrast": 1.5}})

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"]
    # eager -> the task already ran; the WS catch-up sees the finished job
    with client.websocket_connect(body["ws_status_url"]) as ws:
        event = ws.receive_json()
    assert event["status"] == "completed"
    assert event["progress_percent"] == 100


def test_stack_process_enqueues(client, star_field, monkeypatch) -> None:
    import cv2

    ok, png = cv2.imencode(".png", star_field)
    assert ok
    frame = png.tobytes()

    init = client.post("/api/stack/initiate", json={"frame_count": 2})
    stack_id = init.json()["stack_id"]
    for i in range(2):
        client.post(
            f"/api/stack/{stack_id}/upload-frame",
            data={"frame_index": str(i)},
            files={"file": (f"f{i}.png", frame, "image/png")},
        )

    result = client.post(f"/api/stack/{stack_id}/process")
    assert result.status_code == 200
    body = result.json()
    assert body["job_id"]
    assert body["ws_status_url"] == f"/ws/stack-status/{body['job_id']}"
    # eager task ran -> stack is done
    assert client.get(f"/api/stack/{stack_id}").json()["status"] == "completed"
