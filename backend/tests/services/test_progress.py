"""The Redis pub/sub progress plumbing - the best-effort publish/subscribe
contract described in ``app.services.progress``'s module docstring:
``publish`` must never raise even when Redis is down (the job still has to
finish), and ``subscribe`` must filter Redis's own subscribe-confirmation
messages from real progress events.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.services import progress


@pytest.fixture(autouse=True)
def _reset_publisher_state() -> None:
    """``_pub`` is module-level singleton state - reset around every test so
    one test's simulated Redis outage can't leak into the next."""
    progress._pub.disabled = False
    progress._pub.client = None
    yield
    progress._pub.disabled = False
    progress._pub.client = None


def test_publish_never_touches_redis_outside_queue_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """sync mode (the default) is the common case - this must short-circuit
    before ever constructing a Redis client."""

    def _poison(*_a: object, **_k: object) -> None:
        raise AssertionError("from_url should not be called outside queue mode")

    monkeypatch.setattr(progress.redis.Redis, "from_url", staticmethod(_poison))
    progress.publish("job-x", {"status": "processing"})  # must not raise


def test_publish_disables_itself_and_never_raises_when_redis_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROCESSING_MODE", "queue")
    # Port 1 is reserved/unlistened - a fast connection refusal, not a hang.
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    from app.config import get_settings

    get_settings.cache_clear()

    progress.publish("job-x", {"status": "processing"})  # must not raise

    assert progress._pub.disabled is True
    assert progress._pub.client is None

    def _poison(*_a: object, **_k: object) -> None:
        raise AssertionError("a disabled publisher must not reconnect")

    monkeypatch.setattr(progress.redis.Redis, "from_url", staticmethod(_poison))
    progress.publish("job-x", {"status": "processing"})  # still a no-op


class _FakePubSub:
    def __init__(self, messages: list[dict[str, object] | None]) -> None:
        self._messages = list(messages)
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []

    async def subscribe(self, name: str) -> None:
        self.subscribed.append(name)

    async def get_message(self, **_kwargs: object) -> dict[str, object] | None:
        return self._messages.pop(0) if self._messages else None

    async def unsubscribe(self, name: str) -> None:
        self.unsubscribed.append(name)

    async def aclose(self) -> None: ...


class _FakeRedis:
    def __init__(self, messages: list[dict[str, object] | None]) -> None:
        self._pubsub = _FakePubSub(messages)

    def pubsub(self) -> _FakePubSub:
        return self._pubsub

    async def aclose(self) -> None: ...


@pytest.mark.asyncio
async def test_subscribe_filters_confirmations_and_yields_real_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real Redis pubsub channel sends its own subscribe-confirmation message
    first; ``subscribe`` must skip that and yield only the decoded event."""
    messages: list[dict[str, object] | None] = [
        {"type": "subscribe", "data": 1},
        {"type": "message", "data": b'{"status": "processing", "progress_percent": 40}'},
    ]
    fake = _FakeRedis(messages)
    monkeypatch.setattr(progress.aioredis.Redis, "from_url", staticmethod(lambda *_a, **_k: fake))

    gen: AsyncIterator[dict[str, object] | None] = progress.subscribe("job-x", idle_timeout=0.01)
    try:
        event = await gen.__anext__()
    finally:
        await gen.aclose()

    # the subscribe-confirmation message was skipped internally, with no yield -
    # the first thing the caller sees is the real, decoded event.
    assert event == {"status": "processing", "progress_percent": 40}
    assert fake.pubsub().subscribed == [progress.channel("job-x")]
    assert fake.pubsub().unsubscribed == [progress.channel("job-x")]


@pytest.mark.asyncio
async def test_subscribe_decodes_a_string_payload_too(monkeypatch: pytest.MonkeyPatch) -> None:
    """``redis.asyncio`` can hand back ``data`` as ``str`` or ``bytes`` depending
    on ``decode_responses`` - both must decode to the same event."""
    fake = _FakeRedis([{"type": "message", "data": '{"status": "completed"}'}])
    monkeypatch.setattr(progress.aioredis.Redis, "from_url", staticmethod(lambda *_a, **_k: fake))

    gen = progress.subscribe("job-x", idle_timeout=0.01)
    try:
        event = await gen.__anext__()
    finally:
        await gen.aclose()

    assert event == {"status": "completed"}
