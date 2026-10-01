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


def test_streaming_kills_the_engine_when_the_progress_callback_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A job superseded or interrupted mid-pass stops through its progress
    callback - the engine process must not be left running as an orphan."""
    popen = fake_engine_popen(lines=['{"percent": 20}\n', '{"percent": 40}\n'])
    monkeypatch.setattr(external_engine.subprocess, "Popen", popen)

    def _stop(_fraction: float) -> None:
        raise RuntimeError("stop")

    with pytest.raises(RuntimeError, match="stop"):
        _run(engine_image(), progress_cb=_stop)

    assert popen.last is not None
    assert popen.last.killed


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
    """A cache hit is only trusted if the stored array matches the requested
    shape and dtype - a stale or corrupt cache file falls through to recompute."""
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
        external_engine.np, "load", lambda *_a, **_k: np.zeros((8, 8, 3), dtype=np.uint8)
    )

    cache.get_or_compute(image, {"stride": 0}, compute)
    assert len(calls) == 2  # shape mismatch on the cached file -> recomputed


def test_cache_recomputes_when_the_cached_file_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A truncated or corrupt ``.npy`` is treated as a miss, not an error."""
    from app.services.storage import StorageService

    cache = ModelEstimateCache(StorageService(), "sess-cache-4", "tool")
    image = engine_image(64, 64)
    calls: list[int] = []

    def compute() -> np.ndarray:
        calls.append(1)
        return image

    cache.get_or_compute(image, {"stride": 0}, compute)

    def broken(*_a: object, **_k: object) -> np.ndarray:
        raise ValueError("truncated")

    monkeypatch.setattr(external_engine.np, "load", broken)
    cache.get_or_compute(image, {"stride": 0}, compute)
    assert len(calls) == 2


def test_cache_is_lossless_for_16_bit_and_float_estimates() -> None:
    """A 16-bit or float estimate comes back bit-identical - never re-quantised
    to 8 bits the way an image-format cache would."""
    from app.services.storage import StorageService

    cache = ModelEstimateCache(StorageService(), "sess-cache-5", "tool")
    for image in (
        np.random.default_rng(1).integers(0, 65536, (32, 32, 3), dtype=np.uint16),
        np.random.default_rng(2).random((32, 32, 3), dtype=np.float32) * 1e-3,
    ):
        stored = cache.get_or_compute(image, {"stride": 0}, lambda img=image: img)
        served = cache.get_or_compute(image, {"stride": 0}, lambda: pytest.fail("recomputed"))
        assert served.dtype == image.dtype
        assert np.array_equal(served, stored)


def test_16_bit_input_round_trips_at_16_bit(monkeypatch: pytest.MonkeyPatch) -> None:
    """A uint16 image is exchanged as a 16-bit TIFF and comes back uint16, unchanged."""
    monkeypatch.setattr(external_engine.subprocess, "run", fake_engine_run())
    image = np.random.default_rng(3).integers(0, 65536, (600, 800, 3), dtype=np.uint16)

    out = _run(image)

    assert out.dtype == np.uint16
    assert np.array_equal(out, image)


def test_float_input_is_sent_as_linear_fits(monkeypatch: pytest.MonkeyPatch) -> None:
    """float32 input is linear data: it goes through a FITS file with ``--linear``
    and comes back float32, in the same channel order."""
    seen: list[list[str]] = []
    runner = fake_engine_run()

    def run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(cmd)
        return runner(cmd, **kwargs)

    monkeypatch.setattr(external_engine.subprocess, "run", run)
    image = np.random.default_rng(4).random((600, 800, 3), dtype=np.float32) * 0.1
    image[0, 0] = (0.1, 0.2, 0.3)

    out = _run(image)

    assert "--linear" in seen[0]
    assert seen[0][seen[0].index("-i") + 1].endswith(".fits")
    assert out.dtype == np.float32
    assert np.allclose(out, image)
    assert tuple(out[0, 0]) == pytest.approx((0.1, 0.2, 0.3))


def test_float_input_is_clipped_to_the_unit_range_for_the_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tools reject float FITS outside [0, 1]; a star core a hair above 1 is
    clipped on the way in rather than failing the whole pass."""
    monkeypatch.setattr(external_engine.subprocess, "run", fake_engine_run())
    image = np.full((600, 800), 0.5, dtype=np.float32)
    image[10, 10] = 1.3

    out = _run(image)

    assert out.shape == image.shape
    assert float(out.max()) == pytest.approx(1.0)


def test_unreadable_fits_output_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        with open(cmd[cmd.index("-o") + 1], "wb") as handle:
            handle.write(b"not a fits file")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(external_engine.subprocess, "run", run)
    with pytest.raises(ExternalEngineError):
        _run(np.zeros((600, 800, 3), dtype=np.float32))


def test_a_depth_change_by_the_tool_is_undone(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the tool answers a 16-bit request with an 8-bit file, the result is
    rescaled back to the input's depth rather than handed on at the wrong scale."""

    def run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        cv2.imwrite(cmd[cmd.index("-o") + 1], np.full((600, 800, 3), 255, dtype=np.uint8))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(external_engine.subprocess, "run", run)
    out = _run(np.zeros((600, 800, 3), dtype=np.uint16))
    assert out.dtype == np.uint16
    assert int(out.max()) == 65535


def test_lerp_like_and_cast_like_keep_the_reference_dtype() -> None:
    """The blend helpers work at the caller's depth: integers clip and round,
    float only clips below zero."""
    a8 = np.array([[[0, 100, 255]]], dtype=np.uint8)
    b8 = np.array([[[255, 100, 0]]], dtype=np.uint8)
    assert external_engine.lerp_like(a8, b8, 0.5).tolist() == [[[128, 100, 128]]]
    assert external_engine.cast_like(a8, np.array([-5.0, 300.0])).tolist() == [0, 255]

    af = np.array([0.2, 1.5], dtype=np.float32)
    assert external_engine.cast_like(af, np.array([-0.1, 1.5])).tolist() == [0.0, 1.5]
    assert external_engine.lerp_like(af, af * 0, 1.0).dtype == np.float32
