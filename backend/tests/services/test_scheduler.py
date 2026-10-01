"""The in-process scheduler: runs each periodic task, survives a failing run, stops cleanly."""

from __future__ import annotations

import asyncio

import pytest

from app.services import scheduler as scheduler_module
from app.services.scheduler import Scheduler


@pytest.mark.asyncio
async def test_runs_both_tasks_repeatedly_and_survives_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"cleanup": 0, "watch": 0}

    def _cleanup() -> int:
        calls["cleanup"] += 1
        if calls["cleanup"] == 1:
            raise RuntimeError("first cleanup fails")
        return 0

    def _watch() -> str:
        calls["watch"] += 1
        return "disabled"

    monkeypatch.setattr(scheduler_module, "cleanup_expired", _cleanup)
    monkeypatch.setattr(scheduler_module, "watch_stacking_folder", _watch)
    scheduler = Scheduler(cleanup_interval=0.01, watch_interval=0.01, startup_delay=0)

    scheduler.start()
    for _ in range(200):
        if calls["cleanup"] >= 3 and calls["watch"] >= 3:
            break
        await asyncio.sleep(0.01)
    await scheduler.stop()

    assert calls["cleanup"] >= 3  # kept going after the first run raised
    assert calls["watch"] >= 3


@pytest.mark.asyncio
async def test_stop_before_the_first_run(monkeypatch: pytest.MonkeyPatch) -> None:
    ran: list[str] = []
    monkeypatch.setattr(scheduler_module, "cleanup_expired", lambda: ran.append("cleanup"))
    monkeypatch.setattr(scheduler_module, "watch_stacking_folder", lambda: ran.append("watch"))
    scheduler = Scheduler(startup_delay=60)

    scheduler.start()
    await scheduler.stop()

    assert ran == []
