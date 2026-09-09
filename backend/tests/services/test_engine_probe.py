"""Capability probe for the optional StarNet2 / DeepSNR engines."""

from __future__ import annotations

import subprocess
import sys

import pytest

from app.services import engine_probe
from app.services.engine_probe import (
    EngineStatus,
    clear_engine_probe_cache,
    get_engine_statuses,
    probe_engine,
)

_ANY_VERSION = ("0.0.0", "999.0.0")


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_engine_probe_cache()
    yield
    clear_engine_probe_cache()


def test_empty_path_is_not_configured() -> None:
    status = probe_engine("   ", _ANY_VERSION, name="StarNet2")

    assert status.configured is False
    assert status.found is False


def test_missing_binary_is_configured_but_not_found() -> None:
    status = probe_engine("/no/such/starnet2-binary", _ANY_VERSION, name="StarNet2")

    assert status.configured is True
    assert status.found is False
    assert "not found" in status.detail.lower()


def test_real_binary_reports_version_and_known_good() -> None:
    # `python --version` -> "Python 3.x.y": a stand-in for a working engine binary.
    status = probe_engine(sys.executable, ("3.0.0", "4.0.0"), name="Python")

    assert status.found is True
    assert status.version is not None
    assert status.version.startswith("3.")
    assert status.known_good is True
    assert status.detail == f"Python {status.version} detected"


def test_version_outside_the_tested_range_is_found_but_not_known_good() -> None:
    status = probe_engine(sys.executable, ("2.0.0", "3.0.0"), name="Python")

    assert status.found is True
    assert status.known_good is False
    assert "untested" in status.detail


def test_timeout_is_reported_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*_args: object, **_kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd="starnet2", timeout=15)

    monkeypatch.setattr(engine_probe.subprocess, "run", _raise)

    status = probe_engine("/opt/starnet2", _ANY_VERSION, name="StarNet2")

    assert status.found is False
    assert "timed out" in status.detail


def test_runs_but_prints_no_version(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["x"], returncode=0, stdout="hello", stderr="")

    monkeypatch.setattr(engine_probe.subprocess, "run", _fake)

    status = probe_engine("/opt/starnet2", _ANY_VERSION, name="StarNet2")

    assert status.configured is True
    assert status.found is True
    assert status.version is None


def test_nonzero_exit_without_a_version_is_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["x"], returncode=2, stdout="", stderr="boom")

    monkeypatch.setattr(engine_probe.subprocess, "run", _fake)

    status = probe_engine("/opt/starnet2", _ANY_VERSION, name="StarNet2")

    assert status.found is False
    assert "exit 2" in status.detail


def test_get_engine_statuses_memoises_until_cleared(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def _fake_probe(path: str, _tested: tuple[str, str], *, name: str) -> EngineStatus:
        calls.append(name)
        return EngineStatus(configured=bool(path), found=False, detail="stub")

    monkeypatch.setattr(engine_probe, "probe_engine", _fake_probe)

    assert set(get_engine_statuses()) == {"starnet2", "deepsnr"}
    get_engine_statuses()
    assert calls == ["StarNet2", "DeepSNR"]  # second call served from the cache

    clear_engine_probe_cache()
    get_engine_statuses()
    assert calls == ["StarNet2", "DeepSNR", "StarNet2", "DeepSNR"]
