"""Progress WebSocket - DB catch-up, relayed events, idle-tick reconciliation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import WebSocketDisconnect

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


def test_idle_tick_reconciles_a_missed_terminal_event(client, db_session, monkeypatch) -> None:
    """If the job finishes without a pub/sub event reaching the socket (published
    before the subscription, or lost), the idle tick re-reads the DB, sends the
    terminal state, and closes - the client is never left hanging."""
    from app.routes import websockets as ws_mod

    service = JobService(db_session)
    job = service.create("sess-idle")
    service.update(job.job_id, status="processing", progress_percent=40)

    ticks = {"n": 0}

    async def fake_subscribe(_job_id: str, *, idle_timeout: float = 3.0) -> AsyncIterator[None]:
        while True:
            ticks["n"] += 1
            if ticks["n"] == 2:  # the transition the socket "missed"
                JobService(db_session).update(job.job_id, status="completed", progress_percent=100)
            yield None

    monkeypatch.setattr(ws_mod.progress, "subscribe", fake_subscribe)

    with client.websocket_connect(f"/ws/processing-status/{job.job_id}") as sock:
        assert sock.receive_json()["status"] == "processing"  # catch-up
        assert sock.receive_json()["status"] == "completed"  # reconciled on an idle tick


def test_a_real_progress_update_is_relayed_until_terminal(client, db_session, monkeypatch) -> None:
    """A genuine pub/sub update (not an idle None tick) is forwarded as-is, and
    a terminal status in that update ends the stream."""
    from app.routes import websockets as ws_mod

    service = JobService(db_session)
    job = service.create("sess-live")
    service.update(job.job_id, status="processing", progress_percent=10)

    async def fake_subscribe(
        _job_id: str, *, idle_timeout: float = 3.0
    ) -> AsyncIterator[dict[str, Any]]:
        yield {"job_id": job.job_id, "status": "processing", "progress_percent": 55}
        yield {"job_id": job.job_id, "status": "completed", "progress_percent": 100}

    monkeypatch.setattr(ws_mod.progress, "subscribe", fake_subscribe)

    with client.websocket_connect(f"/ws/processing-status/{job.job_id}") as sock:
        assert sock.receive_json()["status"] == "processing"  # catch-up
        assert sock.receive_json()["progress_percent"] == 55  # relayed update
        assert sock.receive_json()["status"] == "completed"  # terminal -> stream ends


def test_a_client_disconnect_mid_stream_ends_quietly(client, db_session, monkeypatch) -> None:
    from app.routes import websockets as ws_mod

    service = JobService(db_session)
    job = service.create("sess-disconnect")
    service.update(job.job_id, status="processing", progress_percent=10)

    async def fake_subscribe(_job_id: str, *, idle_timeout: float = 3.0) -> AsyncIterator[None]:
        raise WebSocketDisconnect
        yield  # pragma: no cover - unreachable, satisfies the async generator shape

    monkeypatch.setattr(ws_mod.progress, "subscribe", fake_subscribe)

    with client.websocket_connect(f"/ws/processing-status/{job.job_id}") as sock:
        assert sock.receive_json()["status"] == "processing"  # catch-up only


def test_an_unexpected_error_mid_stream_closes_the_socket(client, db_session, monkeypatch) -> None:
    """A non-disconnect error while relaying is logged and the socket is
    closed cleanly rather than propagating out of the endpoint."""
    from app.routes import websockets as ws_mod

    service = JobService(db_session)
    job = service.create("sess-error")
    service.update(job.job_id, status="processing", progress_percent=10)

    async def fake_subscribe(_job_id: str, *, idle_timeout: float = 3.0) -> AsyncIterator[None]:
        raise RuntimeError("relay blew up")
        yield  # pragma: no cover - unreachable, satisfies the async generator shape

    monkeypatch.setattr(ws_mod.progress, "subscribe", fake_subscribe)

    with client.websocket_connect(f"/ws/processing-status/{job.job_id}") as sock:
        assert sock.receive_json()["status"] == "processing"  # catch-up only


def test_live_events_published_by_a_job_reach_the_socket(client, db_session) -> None:
    """End to end through the real in-memory broker: an event published from
    another thread while the socket is open is relayed, and a terminal one closes it."""
    import threading
    import time

    from app.services import progress

    service = JobService(db_session)
    job = service.create("sess-broker")
    service.update(job.job_id, status="processing", progress_percent=10)

    def _publish_when_subscribed() -> None:
        deadline = time.monotonic() + 5
        while progress.subscriber_count(job.job_id) == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        progress.publish(
            job.job_id, {"job_id": job.job_id, "status": "processing", "progress_percent": 60}
        )
        progress.publish(
            job.job_id, {"job_id": job.job_id, "status": "completed", "progress_percent": 100}
        )

    publisher = threading.Thread(target=_publish_when_subscribed)
    with client.websocket_connect(f"/ws/processing-status/{job.job_id}") as sock:
        publisher.start()
        assert sock.receive_json()["status"] == "processing"  # catch-up
        assert sock.receive_json()["progress_percent"] == 60
        assert sock.receive_json()["status"] == "completed"
    publisher.join()
    assert progress.subscriber_count(job.job_id) == 0
