"""Progress WebSocket - DB catch-up path (no Redis needed)."""

from __future__ import annotations

from app.services.job import JobService


def test_replays_a_completed_job_then_closes(client, db_session) -> None:
    service = JobService(db_session)
    job = service.create("sess-x")
    service.update(job.job_id, status="completed", progress_percent=100, current_step="done")

    with client.websocket_connect(f"/ws/processing-status/{job.job_id}") as ws:
        event = ws.receive_json()

    assert event["job_id"] == job.job_id
    assert event["status"] == "completed"
    assert event["progress_percent"] == 100


def test_replays_a_failed_job(client, db_session) -> None:
    service = JobService(db_session)
    job = service.create("sess-y")
    service.update(job.job_id, status="failed", error="boom")

    with client.websocket_connect(f"/ws/processing-status/{job.job_id}") as ws:
        event = ws.receive_json()

    assert event["status"] == "failed"
    assert event["error"] == "boom"


def test_unknown_job_reports_unknown(client) -> None:
    with client.websocket_connect("/ws/processing-status/job-missing") as ws:
        event = ws.receive_json()
    assert event["status"] == "unknown"


def test_stack_status_endpoint_is_mounted(client, db_session) -> None:
    job = JobService(db_session).create(None)
    JobService(db_session).update(job.job_id, status="completed", progress_percent=100)
    with client.websocket_connect(f"/ws/stack-status/{job.job_id}") as ws:
        assert ws.receive_json()["status"] == "completed"
