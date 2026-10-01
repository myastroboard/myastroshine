"""JobRunner - runs processing jobs in the background, inside the API process.

MyAstroShine is one container: no queue, no worker process. A ``/process`` or
``/stack/*/process`` call records a :class:`~app.db.models.JobRecord`, submits
the work here and answers at once (``queued``); the client follows the job on
the progress WebSocket (``app.services.progress``).

Two pools, so a long stack never starves the editor:

- ``edit`` - single-image enhancement (``EDIT_JOB_WORKERS`` threads). A burst of
  slider edits mostly supersedes itself (``JobService.supersede_pending_for_session``),
  so a couple of threads keep several sessions responsive.
- ``stack`` - stacking (``STACK_JOB_WORKERS`` thread). A stack is heavy on memory
  and already parallelises its per-frame passes (``stacking_workers``).

Threads, not processes: the heavy lifting is NumPy / OpenCV, which release the
GIL. Shutdown is cooperative - :meth:`JobRunner.shutdown` raises a flag that the
pipelines check between steps (:func:`raise_if_stopping`) and cancels everything
still waiting in a queue.

Under ``APP_ENV=test`` jobs run inline in the submitting thread, so a route test
sees the finished job.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from typing import Literal

from app.config import get_settings
from app.constants import EDIT_JOB_WORKERS, STACK_JOB_WORKERS
from app.exceptions import AppError
from app.logging_config import get_logger

logger = get_logger(__name__)

Pool = Literal["edit", "stack"]


class JobInterruptedError(Exception):
    """The server is shutting down - a running job stops at its next step."""


class JobRunner:
    """Background executor for processing jobs (see the module docstring)."""

    def __init__(self, *, inline: bool = False) -> None:
        self.inline = inline
        self.stopping = threading.Event()
        self._lock = threading.Lock()
        self._futures: set[Future[None]] = set()
        self._pools: dict[Pool, ThreadPoolExecutor] = {
            "edit": ThreadPoolExecutor(EDIT_JOB_WORKERS, thread_name_prefix="edit-job"),
            "stack": ThreadPoolExecutor(STACK_JOB_WORKERS, thread_name_prefix="stack-job"),
        }

    def submit(self, pool: Pool, job_id: str, fn: Callable[[], None]) -> None:
        """Run ``fn`` in the background. Its exceptions are logged, never raised here:
        the job body records its own failure on the job row."""
        if self.stopping.is_set():
            raise JobInterruptedError("The server is shutting down")
        if self.inline:
            self._run(pool, job_id, fn)
            return
        future = self._pools[pool].submit(self._run, pool, job_id, fn)
        with self._lock:
            self._futures.add(future)
        future.add_done_callback(self._forget)

    def _forget(self, future: Future[None]) -> None:
        with self._lock:
            self._futures.discard(future)

    @staticmethod
    def _run(pool: Pool, job_id: str, fn: Callable[[], None]) -> None:
        try:
            fn()
        except JobInterruptedError:
            logger.info("job interrupted by shutdown", pool=pool, job_id=job_id)
        except AppError as exc:
            # Expected failures (session expired, bad stack...) are already on the
            # job row for the client; no traceback needed.
            logger.warning("background job failed", pool=pool, job_id=job_id, error=exc.message)
        except Exception:
            logger.exception("background job failed", pool=pool, job_id=job_id)

    def pending(self) -> int:
        """Jobs submitted and not finished yet (running or waiting)."""
        with self._lock:
            return len(self._futures)

    def shutdown(self, timeout: float) -> bool:
        """Stop: refuse new jobs, drop the waiting ones, give the running ones up to
        ``timeout`` seconds to reach their next step and stop. Returns ``True`` when
        nothing is left running."""
        self.stopping.set()
        for pool in self._pools.values():
            pool.shutdown(wait=False, cancel_futures=True)
        with self._lock:
            running = list(self._futures)
        _done, not_done = wait(running, timeout=timeout)
        if not_done:
            logger.warning("jobs still running at shutdown", count=len(not_done))
        return not not_done


class _Holder:
    """The process-wide runner, held on an instance so helpers never need ``global``."""

    runner: JobRunner | None = None


_holder = _Holder()


def get_job_runner() -> JobRunner:
    """The process-wide runner, created on first use (inline under ``APP_ENV=test``)."""
    if _holder.runner is None:
        _holder.runner = JobRunner(inline=get_settings().is_test)
    return _holder.runner


def reset_job_runner() -> None:
    """Forget the process-wide runner (the next :func:`get_job_runner` builds a
    fresh one) - after a shutdown, and between tests."""
    _holder.runner = None


def raise_if_stopping() -> None:
    """Called by the pipelines between steps: stop now if the server is shutting down."""
    runner = _holder.runner
    if runner is not None and runner.stopping.is_set():
        raise JobInterruptedError("The server is shutting down")
