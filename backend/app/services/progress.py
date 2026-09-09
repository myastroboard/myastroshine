"""Redis pub/sub used to stream job progress to the WebSocket.

Publishing (from the Celery worker) is synchronous and best-effort - if Redis is
down the job still runs, the WebSocket just falls back to DB polling of the final
state. Subscribing (from the async WebSocket handler) uses ``redis.asyncio``.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator

import redis
import redis.asyncio as aioredis

from app.config import get_settings
from app.logging_config import get_logger
from app.types import JsonDict

logger = get_logger(__name__)

_CHANNEL_PREFIX = "myastroshine:job:"
_CONNECT_TIMEOUT = 0.5  # fail fast when Redis is not running


def channel(job_id: str) -> str:
    return f"{_CHANNEL_PREFIX}{job_id}"


class _Publisher:
    """Module-wide state on an instance, so helpers never need ``global``.

    ``disabled`` is set once Redis proves unreachable (stop retrying every step);
    ``client`` is a reused connection - a 1000-frame stack emits hundreds of events.
    """

    disabled: bool = False
    client: redis.Redis | None = None


_pub = _Publisher()


def _enabled() -> bool:
    return get_settings().processing_mode == "queue" and not _pub.disabled


def publish(job_id: str, event: JsonDict) -> None:
    """Best-effort publish of a progress event. Never raises; no-op in sync mode."""
    if not _enabled():
        return
    try:
        if _pub.client is None:
            _pub.client = redis.Redis.from_url(
                get_settings().redis_url,
                socket_connect_timeout=_CONNECT_TIMEOUT,
                socket_timeout=_CONNECT_TIMEOUT,
            )
        _pub.client.publish(channel(job_id), json.dumps(event))
    except Exception as exc:
        _pub.disabled = True
        if _pub.client is not None:
            with contextlib.suppress(Exception):
                _pub.client.close()
            _pub.client = None
        logger.warning("progress publishing disabled (Redis unreachable)", error=str(exc))


async def subscribe(job_id: str, *, idle_timeout: float = 3.0) -> AsyncIterator[JsonDict | None]:
    """Yield progress events for ``job_id`` until the connection drops.

    Yields ``None`` whenever ``idle_timeout`` seconds pass with no event - the
    caller uses that tick to reconcile against the DB, so a terminal event
    published in the gap between the caller's catch-up read and this
    subscription (or lost to a Redis hiccup) can't wedge the stream open.
    """
    client = aioredis.Redis.from_url(
        get_settings().redis_url,
        socket_connect_timeout=_CONNECT_TIMEOUT,
        socket_timeout=_CONNECT_TIMEOUT,
    )
    pubsub = client.pubsub()
    await pubsub.subscribe(channel(job_id))
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=idle_timeout)
            if message is None:
                yield None  # idle tick - caller re-reads the DB
                continue
            if message.get("type") != "message":
                continue
            data = message["data"]
            yield json.loads(data.decode() if isinstance(data, bytes) else data)
    finally:
        await pubsub.unsubscribe(channel(job_id))
        await pubsub.aclose()  # type: ignore[no-untyped-call]
        await client.aclose()
