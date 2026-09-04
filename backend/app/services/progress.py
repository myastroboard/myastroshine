"""Redis pub/sub used to stream job progress to the WebSocket.

Publishing (from the Celery worker) is synchronous and best-effort - if Redis is
down the job still runs, the WebSocket just falls back to DB polling of the final
state. Subscribing (from the async WebSocket handler) uses ``redis.asyncio``.
"""

from __future__ import annotations

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


# set once Redis proves unreachable, so we stop retrying it every step
_state = {"publish_disabled": False}


def _enabled() -> bool:
    return get_settings().processing_mode == "queue" and not _state["publish_disabled"]


def publish(job_id: str, event: JsonDict) -> None:
    """Best-effort publish of a progress event. Never raises; no-op in sync mode."""
    if not _enabled():
        return
    try:
        client = redis.Redis.from_url(
            get_settings().redis_url,
            socket_connect_timeout=_CONNECT_TIMEOUT,
            socket_timeout=_CONNECT_TIMEOUT,
        )
        client.publish(channel(job_id), json.dumps(event))
        client.close()
    except Exception as exc:
        _state["publish_disabled"] = True
        logger.warning("progress publishing disabled (Redis unreachable)", error=str(exc))


async def subscribe(job_id: str) -> AsyncIterator[JsonDict]:
    """Yield progress events for ``job_id`` until the connection drops."""
    client = aioredis.Redis.from_url(
        get_settings().redis_url,
        socket_connect_timeout=_CONNECT_TIMEOUT,
        socket_timeout=_CONNECT_TIMEOUT,
    )
    pubsub = client.pubsub()
    await pubsub.subscribe(channel(job_id))
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            data = message["data"]
            yield json.loads(data.decode() if isinstance(data, bytes) else data)
    finally:
        await pubsub.unsubscribe(channel(job_id))
        await pubsub.aclose()  # type: ignore[no-untyped-call]
        await client.aclose()
