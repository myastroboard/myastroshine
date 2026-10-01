"""The in-process progress broker (``app.services.progress``): events published
from job threads reach the WebSocket subscribers of that job, and nobody else."""

from __future__ import annotations

import asyncio
import threading

import pytest

from app.services import progress


async def _next(gen, timeout: float = 2.0):
    return await asyncio.wait_for(gen.__anext__(), timeout=timeout)


@pytest.mark.asyncio
async def test_publish_without_subscribers_is_a_silent_no_op() -> None:
    """A job with nobody watching must never fail because of it."""
    progress.publish("job-nobody", {"status": "processing"})

    assert progress.subscriber_count("job-nobody") == 0


@pytest.mark.asyncio
async def test_subscriber_receives_events_for_its_job_only() -> None:
    gen = progress.subscribe("job-a", idle_timeout=5)
    first = asyncio.ensure_future(_next(gen))
    await asyncio.sleep(0)  # let the generator register its queue

    progress.publish("job-b", {"status": "processing", "job_id": "job-b"})
    progress.publish("job-a", {"status": "processing", "job_id": "job-a"})

    assert (await first)["job_id"] == "job-a"
    await gen.aclose()


@pytest.mark.asyncio
async def test_events_published_from_another_thread_are_delivered_in_order() -> None:
    """Jobs run on background threads; ``publish`` must be thread-safe."""
    gen = progress.subscribe("job-t", idle_timeout=5)
    first = asyncio.ensure_future(_next(gen))
    await asyncio.sleep(0)

    def _publish() -> None:
        for percent in (10, 50, 100):
            progress.publish("job-t", {"progress_percent": percent})

    thread = threading.Thread(target=_publish)
    thread.start()
    thread.join()

    received = [(await first)["progress_percent"]]
    received += [(await _next(gen))["progress_percent"] for _ in range(2)]
    assert received == [10, 50, 100]
    await gen.aclose()


@pytest.mark.asyncio
async def test_every_subscriber_of_a_job_gets_the_event() -> None:
    first_gen = progress.subscribe("job-m", idle_timeout=5)
    second_gen = progress.subscribe("job-m", idle_timeout=5)
    first = asyncio.ensure_future(_next(first_gen))
    second = asyncio.ensure_future(_next(second_gen))
    await asyncio.sleep(0)
    assert progress.subscriber_count("job-m") == 2

    progress.publish("job-m", {"status": "completed"})

    assert (await first)["status"] == (await second)["status"] == "completed"
    await first_gen.aclose()
    assert progress.subscriber_count("job-m") == 1
    await second_gen.aclose()
    assert progress.subscriber_count("job-m") == 0


@pytest.mark.asyncio
async def test_subscribe_yields_none_on_idle() -> None:
    """With no event for ``idle_timeout``, the subscriber gets a ``None`` tick so the
    socket handler can re-read the job from the DB."""
    gen = progress.subscribe("job-idle", idle_timeout=0.01)

    assert await _next(gen) is None
    await gen.aclose()
    assert progress.subscriber_count("job-idle") == 0


def test_publish_to_a_subscriber_whose_loop_is_closed_does_not_raise() -> None:
    """At shutdown a socket's loop can close while a job thread still publishes."""
    loop = asyncio.new_event_loop()
    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
    loop.close()
    with progress._broker.lock:
        progress._broker.subscribers["job-closed"] = [(loop, queue)]
    try:
        progress.publish("job-closed", {"status": "processing"})  # must not raise
    finally:
        with progress._broker.lock:
            progress._broker.subscribers.pop("job-closed", None)
