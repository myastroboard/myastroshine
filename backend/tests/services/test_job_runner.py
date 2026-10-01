"""JobRunner: background pools, inline test mode, failure logging, cooperative shutdown."""

from __future__ import annotations

import threading

import pytest

from app.exceptions import SessionNotFoundError
from app.services import job_runner
from app.services.job_runner import (
    JobInterruptedError,
    JobRunner,
    get_job_runner,
    raise_if_stopping,
    reset_job_runner,
)


def test_inline_runner_runs_the_job_before_submit_returns() -> None:
    runner = JobRunner(inline=True)
    ran: list[str] = []

    runner.submit("edit", "job-1", lambda: ran.append("done"))

    assert ran == ["done"]
    assert runner.pending() == 0


def test_threaded_runner_runs_jobs_off_the_calling_thread() -> None:
    runner = JobRunner()
    seen: list[str] = []
    done = threading.Event()

    def _job() -> None:
        seen.append(threading.current_thread().name)
        done.set()

    runner.submit("stack", "job-2", _job)

    assert done.wait(5)
    assert seen[0].startswith("stack-job")
    assert runner.shutdown(timeout=5)


@pytest.mark.parametrize(
    "error",
    [RuntimeError("boom"), SessionNotFoundError("gone"), JobInterruptedError("stop")],
)
def test_a_failing_job_is_contained(error: Exception) -> None:
    """Whatever a job raises stays in the job: submit never raises it, the pool
    keeps working."""
    runner = JobRunner(inline=True)

    def _fail() -> None:
        raise error

    runner.submit("edit", "job-3", _fail)
    ran: list[int] = []
    runner.submit("edit", "job-4", lambda: ran.append(1))

    assert ran == [1]


def test_shutdown_stops_running_jobs_at_their_next_step_and_drops_queued_ones() -> None:
    """The running job sees the stop flag through raise_if_stopping; the job
    waiting behind it in the single-thread stack pool never starts."""
    runner = JobRunner()
    job_runner._holder.runner = runner
    started = threading.Event()
    outcome: list[str] = []

    def _long_job() -> None:
        started.set()
        while True:
            try:
                raise_if_stopping()
            except JobInterruptedError:
                outcome.append("interrupted")
                raise
            threading.Event().wait(0.01)

    try:
        runner.submit("stack", "job-long", _long_job)
        runner.submit("stack", "job-waiting", lambda: outcome.append("waiting job ran"))
        assert started.wait(5)

        assert runner.shutdown(timeout=5) is True
    finally:
        reset_job_runner()

    assert outcome == ["interrupted"]
    assert runner.pending() == 0


def test_shutdown_reports_a_job_that_outlives_the_grace_period() -> None:
    runner = JobRunner()
    release = threading.Event()
    started = threading.Event()

    def _stubborn() -> None:  # never checks the stop flag
        started.set()
        release.wait(5)

    runner.submit("edit", "job-stubborn", _stubborn)
    assert started.wait(5)

    assert runner.shutdown(timeout=0.05) is False
    release.set()


def test_submit_after_shutdown_is_refused() -> None:
    runner = JobRunner()
    runner.shutdown(timeout=1)

    with pytest.raises(JobInterruptedError):
        runner.submit("edit", "job-late", lambda: None)


def test_get_job_runner_is_a_process_wide_inline_runner_in_tests() -> None:
    first = get_job_runner()

    assert first is get_job_runner()
    assert first.inline is True
    reset_job_runner()
    assert get_job_runner() is not first


def test_raise_if_stopping_is_quiet_without_a_runner_or_before_shutdown() -> None:
    reset_job_runner()
    raise_if_stopping()  # no runner yet

    get_job_runner()
    raise_if_stopping()  # runner, not stopping
