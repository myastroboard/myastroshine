"""Shared runner + cache for the starnetastro CLI engines. Binary is mocked."""

from __future__ import annotations

import subprocess

import cv2
import numpy as np
import pytest

from app.services import external_engine
from app.services.external_engine import (
    ExternalEngineError,
    ModelEstimateCache,
    _parse_progress,
    run_cli,
)
from tests.support import (
    ImmediateTimer,
    engine_image,
    fake_engine_popen,
    fake_engine_run,
)


def _run(image: np.ndarray, **kwargs: object) -> np.ndarray:
    return run_cli("/opt/tool", image, name="Tool", **kwargs)  # type: ignore[arg-type]


def test_round_trips_shape_and_dtype(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(external_engine.subprocess, "run", fake_engine_run())

    out = _run(engine_image())

    assert out.shape == (600, 800, 3)
    assert out.dtype == np.uint8


def test_stride_is_passed_through_only_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(cmd)
        cv2.imwrite(cmd[cmd.index("-o") + 1], cv2.imread(cmd[cmd.index("-i") + 1]))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(external_engine.subprocess, "run", run)

    _run(engine_image(), stride=64)
    assert "-s" in seen[0] and seen[0][seen[0].index("-s") + 1] == "64"

    seen.clear()
    _run(engine_image(), stride=0)
    assert "-s" not in seen[0]


@pytest.mark.parametrize(
    "runner",
    [fake_engine_run(returncode=1, write_output=False), fake_engine_run(write_output=False)],
)
def test_failure_modes_raise(monkeypatch: pytest.MonkeyPatch, runner) -> None:
    monkeypatch.setattr(external_engine.subprocess, "run", runner)
    with pytest.raises(ExternalEngineError):
        _run(engine_image())


def test_missing_binary_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(*_args: object, **_kwargs: object) -> object:
        raise FileNotFoundError

    monkeypatch.setattr(external_engine.subprocess, "run", run)
    with pytest.raises(ExternalEngineError):
        _run(engine_image())


def test_timeout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(*_args: object, **_kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd="tool", timeout=900)

    monkeypatch.setattr(external_engine.subprocess, "run", run)
    with pytest.raises(ExternalEngineError):
        _run(engine_image())


def test_small_image_is_upscaled_for_the_tool_and_restored(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, tuple[int, ...]] = {}

    def run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        source = cv2.imread(cmd[cmd.index("-i") + 1], cv2.IMREAD_COLOR)
        seen["shape"] = source.shape
        cv2.imwrite(cmd[cmd.index("-o") + 1], source)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(external_engine.subprocess, "run", run)

    out = _run(engine_image(200, 300))

    assert min(seen["shape"][:2]) >= 512  # the tool never sees a side below its minimum
    assert out.shape == (200, 300, 3)  # and the caller gets the original size back


def test_unwritable_input_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """cv2.imwrite failing on the input TIFF (e.g. a full disk) is a clean
    ExternalEngineError, not a crash."""
    monkeypatch.setattr(external_engine.cv2, "imwrite", lambda *_a, **_k: False)
    with pytest.raises(ExternalEngineError, match="could not write"):
        _run(engine_image())


def test_unreadable_output_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """The tool exits 0 and writes *something* to -o, but it isn't a valid image."""

    def run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        with open(cmd[cmd.index("-o") + 1], "wb") as fh:
            fh.write(b"not a tiff file")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(external_engine.subprocess, "run", run)
    with pytest.raises(ExternalEngineError, match="unreadable"):
        _run(engine_image())


def test_output_of_a_different_shape_is_resized_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """The tool is expected to preserve shape, but if it doesn't the result is
    resized back to the input's shape rather than returned mismatched."""

    def run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        cv2.imwrite(cmd[cmd.index("-o") + 1], engine_image(64, 64))  # wrong shape on purpose
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(external_engine.subprocess, "run", run)
    out = _run(engine_image())
    assert out.shape == (600, 800, 3)  # resized back to the input's shape


# --- progress streaming (--machine-progress) --------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('{"schema":"starnetastro.cli.progress.v1","event":"progress","percent":25.0}', 0.25),
        ('{"progress": 0.42}', 0.42),
        ('  {"fraction": 0.5}  \n', 0.5),
        ('{"done": 1}', 1.0),
        ("not json at all", None),
        ('{"unrelated": 3}', None),
        ("[1, 2, 3]", None),
        ('{"progress": true}', None),
        ('{"percent": 250}', 1.0),
        ('{"broken": ', None),  # starts with "{" but fails to parse
    ],
)
def test_parse_progress_is_tolerant(line: str, expected: float | None) -> None:
    assert _parse_progress(line) == expected


def test_streaming_forwards_each_progress_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        external_engine.subprocess,
        "Popen",
        fake_engine_popen(lines=['{"percent": 20}\n', "chatter\n", '{"percent": 90}\n']),
    )
    seen: list[float] = []

    _run(engine_image(), progress_cb=seen.append)

    assert seen == [0.2, 0.9]


def test_streaming_adds_the_machine_progress_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    record: list[list[str]] = []
    monkeypatch.setattr(external_engine.subprocess, "Popen", fake_engine_popen(record=record))

    _run(engine_image(), progress_cb=lambda _f: None)

    assert "--machine-progress" in record[0]


def test_streaming_nonzero_exit_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        external_engine.subprocess,
        "Popen",
        fake_engine_popen(returncode=3, write_output=False, lines=["boom\n"]),
    )
    with pytest.raises(ExternalEngineError, match="exited 3"):
        _run(engine_image(), progress_cb=lambda _f: None)


def test_streaming_missing_binary_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def popen(*_a: object, **_k: object) -> object:
        raise FileNotFoundError

    monkeypatch.setattr(external_engine.subprocess, "Popen", popen)
    with pytest.raises(ExternalEngineError, match="did not run"):
        _run(engine_image(), progress_cb=lambda _f: None)


def test_streaming_timeout_kills_and_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(external_engine.threading, "Timer", ImmediateTimer)
    monkeypatch.setattr(external_engine.subprocess, "Popen", fake_engine_popen())

    with pytest.raises(ExternalEngineError, match="timed out"):
        _run(engine_image(), progress_cb=lambda _f: None)


# --- ModelEstimateCache -----------------------------------------------------


def test_cache_computes_once_then_serves_from_disk() -> None:
    from app.services.storage import StorageService

    cache = ModelEstimateCache(StorageService(), "sess-cache-1", "tool")
    image = engine_image(64, 64)
    calls: list[int] = []

    def compute() -> np.ndarray:
        calls.append(1)
        return cv2.GaussianBlur(image, (0, 0), 2)

    first = cache.get_or_compute(image, {"stride": 0}, compute)
    second = cache.get_or_compute(image, {"stride": 0}, compute)

    assert len(calls) == 1
    assert np.array_equal(first, second)


def test_cache_key_separates_images_and_settings() -> None:
    from app.services.storage import StorageService

    cache = ModelEstimateCache(StorageService(), "sess-cache-2", "tool")
    image = engine_image(64, 64)
    other = engine_image(64, 64) ^ 1  # one bit different
    calls: list[int] = []

    def compute() -> np.ndarray:
        calls.append(1)
        return image

    cache.get_or_compute(image, {"stride": 0}, compute)
    cache.get_or_compute(image, {"stride": 2}, compute)  # different settings
    cache.get_or_compute(other, {"stride": 0}, compute)  # different pixels

    assert len(calls) == 3


def test_cache_recomputes_when_the_cached_file_has_the_wrong_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cache hit is only trusted if the decoded image matches the requested
    shape - a stale or corrupt cache file falls through to recompute."""
    from app.services.storage import StorageService

    cache = ModelEstimateCache(StorageService(), "sess-cache-3", "tool")
    image = engine_image(64, 64)
    calls: list[int] = []

    def compute() -> np.ndarray:
        calls.append(1)
        return image

    cache.get_or_compute(image, {"stride": 0}, compute)
    assert len(calls) == 1

    monkeypatch.setattr(
        external_engine.cv2, "imread", lambda *_a, **_k: np.zeros((8, 8, 3), dtype=np.uint8)
    )

    cache.get_or_compute(image, {"stride": 0}, compute)
    assert len(calls) == 2  # shape mismatch on the cached file -> recomputed
