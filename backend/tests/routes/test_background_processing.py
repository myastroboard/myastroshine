"""Processing routes hand their work to the background job runner.

Under ``APP_ENV=test`` the runner runs jobs inline, so the job is already
finished when the route answers; the tests below also hold the job back to see
the "queued" answer a real client gets.
"""

from __future__ import annotations

import pytest

from app.services.job_runner import get_job_runner


def _upload(client, sample_jpeg: bytes) -> str:
    return client.post(
        "/api/upload", files={"file": ("m31.jpg", sample_jpeg, "image/jpeg")}
    ).json()["session_id"]


def _stack_with_two_frames(client, star_field) -> str:
    import cv2

    ok, png = cv2.imencode(".png", star_field)
    assert ok
    init = client.post("/api/stack/initiate", json={"frame_count": 2})
    stack_id = init.json()["stack_id"]
    for i in range(2):
        client.post(
            f"/api/stack/{stack_id}/upload-frame",
            data={"frame_index": str(i)},
            files={"file": (f"f{i}.png", png.tobytes(), "image/png")},
        )
    return stack_id


def test_process_runs_the_job_and_the_socket_sees_it_finished(client, sample_jpeg: bytes) -> None:
    session_id = _upload(client, sample_jpeg)

    response = client.post(f"/api/process/{session_id}", json={"parameters": {"contrast": 1.5}})

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"]
    with client.websocket_connect(body["ws_status_url"]) as ws:
        event = ws.receive_json()
    assert event["status"] == "completed"
    assert event["progress_percent"] == 100


def test_process_answers_queued_while_the_job_waits(
    client, sample_jpeg: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route never waits for the pipeline: it answers with the queued job."""
    session_id = _upload(client, sample_jpeg)
    submitted: list[tuple[str, str]] = []
    monkeypatch.setattr(
        get_job_runner(), "submit", lambda pool, job_id, _fn: submitted.append((pool, job_id))
    )

    body = client.post(f"/api/process/{session_id}", json={"parameters": {}}).json()

    assert body["status"] == "queued"
    assert submitted == [("edit", body["job_id"])]


def test_a_failing_job_is_reported_on_the_job_not_as_an_http_error(
    client, sample_jpeg: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pipeline runs after the answer, so its failure lands on the job row."""
    from app.services.image_processing import ImageProcessingService

    session_id = _upload(client, sample_jpeg)

    def _boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("pipeline exploded")

    monkeypatch.setattr(ImageProcessingService, "apply_parameters", _boom)

    response = client.post(f"/api/process/{session_id}", json={"parameters": {}})

    assert response.status_code == 200
    assert response.json()["status"] == "failed"


def test_stack_process_runs_the_stack_job(client, star_field) -> None:
    stack_id = _stack_with_two_frames(client, star_field)

    result = client.post(f"/api/stack/{stack_id}/process")

    assert result.status_code == 200
    body = result.json()
    assert body["job_id"]
    assert body["ws_status_url"] == f"/ws/stack-status/{body['job_id']}"
    assert client.get(f"/api/stack/{stack_id}").json()["status"] == "completed"
