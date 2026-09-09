"""StarNet2-backed starless split. The binary is mocked - no real tool in CI."""

from __future__ import annotations

import subprocess

import cv2
import numpy as np
import pytest

from app.services import external_starless
from app.services.external_starless import (
    ExternalStarlessError,
    ExternalStarlessService,
    StarlessModelCache,
    _parse_progress,
    blend_starless,
)


def _image(height: int = 600, width: int = 800) -> np.ndarray:
    return np.random.default_rng(0).integers(0, 256, (height, width, 3), dtype=np.uint8)


def _fake_starnet2(*, returncode: int = 0, write_output: bool = True):
    """A stand-in for the binary (blocking path): copies the input TIFF to output."""

    def run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if write_output and returncode == 0:
            source = cv2.imread(cmd[cmd.index("-i") + 1], cv2.IMREAD_COLOR)
            cv2.imwrite(cmd[cmd.index("-o") + 1], source)
        return subprocess.CompletedProcess(
            cmd, returncode, stdout="", stderr="boom" if returncode else ""
        )

    return run


def _fake_popen(
    *,
    returncode: int = 0,
    write_output: bool = True,
    lines: list[str] | None = None,
    record: list[list[str]] | None = None,
):
    """A stand-in for ``Popen`` (streaming path): copies the TIFF, yields progress."""
    progress_lines = lines if lines is not None else ['{"progress": 1.0}\n']

    class _Popen:
        def __init__(self, cmd: list[str], **_kwargs: object) -> None:
            if record is not None:
                record.append(cmd)
            self.args = cmd
            if write_output and returncode == 0:
                source = cv2.imread(cmd[cmd.index("-i") + 1], cv2.IMREAD_COLOR)
                cv2.imwrite(cmd[cmd.index("-o") + 1], source)
            self.stdout = iter(progress_lines)
            self.returncode = returncode

        def wait(self, timeout: float | None = None) -> int:
            return self.returncode

        def kill(self) -> None:
            self.returncode = -9

    return _Popen


def test_run_model_round_trips_shape_and_dtype(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(external_starless.subprocess, "run", _fake_starnet2())

    out = ExternalStarlessService("/opt/starnet2").run_model(_image())

    assert out.shape == (600, 800, 3)
    assert out.dtype == np.uint8


def test_stride_is_passed_through_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(cmd)
        cv2.imwrite(cmd[cmd.index("-o") + 1], cv2.imread(cmd[cmd.index("-i") + 1]))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(external_starless.subprocess, "run", run)

    ExternalStarlessService("/opt/starnet2", stride=64).run_model(_image())
    assert "-s" in seen[0] and seen[0][seen[0].index("-s") + 1] == "64"

    seen.clear()
    ExternalStarlessService("/opt/starnet2", stride=0).run_model(_image())
    assert "-s" not in seen[0]


@pytest.mark.parametrize(
    "runner",
    [
        _fake_starnet2(returncode=1, write_output=False),
        _fake_starnet2(write_output=False),
    ],
)
def test_failure_modes_raise_external_error(monkeypatch: pytest.MonkeyPatch, runner) -> None:
    monkeypatch.setattr(external_starless.subprocess, "run", runner)
    with pytest.raises(ExternalStarlessError):
        ExternalStarlessService("/opt/starnet2").run_model(_image())


def test_missing_binary_raises_external_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(*_args: object, **_kwargs: object) -> object:
        raise FileNotFoundError

    monkeypatch.setattr(external_starless.subprocess, "run", run)
    with pytest.raises(ExternalStarlessError):
        ExternalStarlessService("/no/starnet2").run_model(_image())


def test_timeout_raises_external_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(*_args: object, **_kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd="starnet2", timeout=600)

    monkeypatch.setattr(external_starless.subprocess, "run", run)
    with pytest.raises(ExternalStarlessError):
        ExternalStarlessService("/opt/starnet2").run_model(_image())


def test_small_image_is_upscaled_for_the_tool_and_restored(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, tuple[int, ...]] = {}

    def run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        source = cv2.imread(cmd[cmd.index("-i") + 1], cv2.IMREAD_COLOR)
        seen["shape"] = source.shape
        cv2.imwrite(cmd[cmd.index("-o") + 1], source)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(external_starless.subprocess, "run", run)

    out = ExternalStarlessService("/opt/starnet2").run_model(_image(200, 300))

    assert min(seen["shape"][:2]) >= 512  # the tool never sees a side below its minimum
    assert out.shape == (200, 300, 3)  # and the caller gets the original size back


def test_blend_at_zero_is_the_original() -> None:
    image = _image(64, 64)
    starless, stars = blend_starless(image, np.zeros_like(image), 0)

    assert np.array_equal(starless, image)
    assert not stars.any()


def test_blend_at_full_strength_is_the_estimate_plus_star_flux() -> None:
    image = np.full((8, 8, 3), 200, np.uint8)
    estimate = np.full((8, 8, 3), 50, np.uint8)

    starless, stars = blend_starless(image, estimate, 100)

    assert np.array_equal(starless, estimate)
    assert np.array_equal(stars, np.full((8, 8, 3), 150, np.uint8))


def test_split_matches_the_classical_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(external_starless.subprocess, "run", _fake_starnet2())

    starless, stars = ExternalStarlessService("/opt/starnet2").split(_image(), 50, 30, 100)

    assert starless.shape == stars.shape == (600, 800, 3)


def test_cache_computes_once_then_serves_from_disk() -> None:
    from app.services.storage import StorageService

    cache = StarlessModelCache(StorageService(), "sess-cache-1")
    image = _image(64, 64)
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

    cache = StarlessModelCache(StorageService(), "sess-cache-2")
    image = _image(64, 64)
    other = _image(64, 64) ^ 1  # one bit different
    calls: list[int] = []

    def compute() -> np.ndarray:
        calls.append(1)
        return image

    cache.get_or_compute(image, {"stride": 0}, compute)
    cache.get_or_compute(image, {"stride": 2}, compute)  # different settings
    cache.get_or_compute(other, {"stride": 0}, compute)  # different pixels

    assert len(calls) == 3


# --- progress streaming (--machine-progress) --------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('{"progress": 0.42}', 0.42),
        ('{"percent": 75}', 0.75),
        ('  {"fraction": 0.5}  \n', 0.5),
        ('{"done": 1}', 1.0),
        ("not json at all", None),
        ('{"unrelated": 3}', None),
        ("[1, 2, 3]", None),
        ('{"progress": true}', None),
        ('{"progress": 250}', 1.0),
    ],
)
def test_parse_progress_is_tolerant(line: str, expected: float | None) -> None:
    assert _parse_progress(line) == expected


def test_streaming_forwards_each_progress_line_to_the_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        external_starless.subprocess,
        "Popen",
        _fake_popen(lines=['{"progress": 0.2}\n', "chatter\n", '{"percent": 90}\n']),
    )
    seen: list[float] = []

    ExternalStarlessService("/opt/starnet2", progress_cb=seen.append).run_model(_image())

    assert seen == [0.2, 0.9]


def test_streaming_path_adds_the_machine_progress_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    record: list[list[str]] = []
    monkeypatch.setattr(external_starless.subprocess, "Popen", _fake_popen(record=record))

    ExternalStarlessService("/opt/starnet2", progress_cb=lambda _f: None).run_model(_image())

    assert "--machine-progress" in record[0]


def test_streaming_nonzero_exit_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        external_starless.subprocess,
        "Popen",
        _fake_popen(returncode=3, write_output=False, lines=["boom\n"]),
    )
    with pytest.raises(ExternalStarlessError, match="exited 3"):
        ExternalStarlessService("/opt/starnet2", progress_cb=lambda _f: None).run_model(_image())


def test_streaming_timeout_kills_and_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class _ImmediateTimer:
        def __init__(self, _interval: float, fn) -> None:
            self._fn = fn

        def start(self) -> None:
            self._fn()

        def cancel(self) -> None:
            pass

    monkeypatch.setattr(external_starless.threading, "Timer", _ImmediateTimer)
    monkeypatch.setattr(external_starless.subprocess, "Popen", _fake_popen())

    with pytest.raises(ExternalStarlessError, match="timed out"):
        ExternalStarlessService("/opt/starnet2", progress_cb=lambda _f: None).run_model(_image())
