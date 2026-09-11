"""Progress WebSocket - DB catch-up path (no Redis needed)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
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
        raise RuntimeError("redis blew up")
        yield  # pragma: no cover - unreachable, satisfies the async generator shape

    monkeypatch.setattr(ws_mod.progress, "subscribe", fake_subscribe)

    with client.websocket_connect(f"/ws/processing-status/{job.job_id}") as sock:
        assert sock.receive_json()["status"] == "processing"  # catch-up only


@pytest.mark.asyncio
async def test_subscribe_yields_none_on_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    """progress.subscribe emits an idle tick so the socket handler can poll."""
    from app.services import progress

    class _FakePubSub:
        async def subscribe(self, *_a: object) -> None: ...
        async def get_message(self, **_k: object) -> None: ...  # always idle
        async def unsubscribe(self, *_a: object) -> None: ...
        async def aclose(self) -> None: ...

    class _FakeRedis:
        def pubsub(self) -> _FakePubSub:
            return _FakePubSub()

        async def aclose(self) -> None: ...

    monkeypatch.setattr(
        progress.aioredis.Redis, "from_url", staticmethod(lambda *_a, **_k: _FakeRedis())
    )

    gen = progress.subscribe("job-x", idle_timeout=0.01)
    try:
        assert await gen.__anext__() is None
    finally:
        await gen.aclose()
