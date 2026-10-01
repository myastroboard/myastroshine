"""In-process periodic tasks, started and stopped with the application.

Two loops, each running its task in a worker thread (``asyncio.to_thread``) so
the event loop never blocks:

- the cleanup (expired sessions / stacks / jobs / admin logins), hourly;
- the watch-folder poll, every minute (a no-op unless ``stacking_watch_dir`` is set).

A failing run is logged and the loop carries on - one bad tick must never stop
the maintenance for the life of the process.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from typing import Any

from app.constants import SESSION_CLEANUP_INTERVAL_SECONDS, STACK_WATCH_INTERVAL_SECONDS
from app.logging_config import get_logger
from app.services.background_jobs import cleanup_expired, watch_stacking_folder

logger = get_logger(__name__)


async def _every(name: str, interval: float, task: Callable[[], Any], *, delay: float) -> None:
    """Run ``task`` after ``delay`` seconds, then every ``interval`` seconds, forever."""
    await asyncio.sleep(delay)
    while True:
        try:
            result = await asyncio.to_thread(task)
            logger.debug("scheduled task ran", task=name, result=result)
        except Exception:
            logger.exception("scheduled task failed", task=name)
        await asyncio.sleep(interval)


class Scheduler:
    """Owns the periodic loops; :meth:`start` in the lifespan startup, :meth:`stop` at shutdown."""

    def __init__(
        self,
        *,
        cleanup_interval: float = SESSION_CLEANUP_INTERVAL_SECONDS,
        watch_interval: float = STACK_WATCH_INTERVAL_SECONDS,
        startup_delay: float = 5.0,
    ) -> None:
        self._specs: list[tuple[str, float, Callable[[], Any]]] = [
            ("cleanup", cleanup_interval, cleanup_expired),
            ("watch-folder", watch_interval, watch_stacking_folder),
        ]
        self._startup_delay = startup_delay
        self._tasks: list[asyncio.Task[None]] = []

    def start(self) -> None:
        for name, interval, task in self._specs:
            self._tasks.append(
                asyncio.create_task(
                    _every(name, interval, task, delay=self._startup_delay),
                    name=f"scheduler-{name}",
                )
            )

    async def stop(self) -> None:
        """Cancel the loops (a run in progress finishes in its thread, unobserved)."""
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
