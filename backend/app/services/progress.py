"""In-process pub/sub that streams job progress to the WebSocket.

Jobs run on background threads of this same process (``app.services.job_runner``)
and ``publish`` their progress events; each open progress socket ``subscribe``s
to its job from the event loop. The two meet here: an ``asyncio.Queue`` per
subscriber, fed from any thread with ``loop.call_soon_threadsafe``.

Best-effort by design: ``publish`` never raises and never blocks, and an event
with no subscriber is simply dropped - the WebSocket first sends the job's state
from the DB (catch-up) and re-reads the DB on every idle tick, so a missed event
can never leave a client hanging.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator

from app.logging_config import get_logger
from app.types import JsonDict

logger = get_logger(__name__)

_Subscriber = tuple[asyncio.AbstractEventLoop, "asyncio.Queue[JsonDict]"]


class _Broker:
    """Module-wide subscriber registry, held on an instance so helpers never need ``global``."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.subscribers: dict[str, list[_Subscriber]] = {}


_broker = _Broker()


def publish(job_id: str, event: JsonDict) -> None:
    """Hand ``event`` to every socket following ``job_id``. Never raises."""
    with _broker.lock:
        targets = list(_broker.subscribers.get(job_id, ()))
    for loop, queue in targets:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, event)
        except RuntimeError:
            # The subscriber's loop closed under us (shutdown) - nobody to tell.
            logger.debug("progress subscriber loop closed", job_id=job_id)


def subscriber_count(job_id: str) -> int:
    """How many sockets follow ``job_id`` (diagnostics and tests)."""
    with _broker.lock:
        return len(_broker.subscribers.get(job_id, ()))


async def subscribe(job_id: str, *, idle_timeout: float = 3.0) -> AsyncIterator[JsonDict | None]:
    """Yield progress events for ``job_id`` until the caller stops iterating.

    Yields ``None`` whenever ``idle_timeout`` seconds pass with no event - the
    caller uses that tick to reconcile against the DB, so a terminal event
    published before this subscription existed can't wedge the stream open.
    """
    queue: asyncio.Queue[JsonDict] = asyncio.Queue()
    entry: _Subscriber = (asyncio.get_running_loop(), queue)
    with _broker.lock:
        _broker.subscribers.setdefault(job_id, []).append(entry)
    try:
        while True:
            try:
                yield await asyncio.wait_for(queue.get(), timeout=idle_timeout)
            except TimeoutError:
                yield None  # idle tick - caller re-reads the DB
    finally:
        with _broker.lock:
            remaining = [s for s in _broker.subscribers.get(job_id, ()) if s is not entry]
            if remaining:
                _broker.subscribers[job_id] = remaining
            else:
                _broker.subscribers.pop(job_id, None)
