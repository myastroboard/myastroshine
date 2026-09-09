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
    blend_starless,
)


def _image(height: int = 600, width: int = 800) -> np.ndarray:
    return np.random.default_rng(0).integers(0, 256, (height, width, 3), dtype=np.uint8)


def _fake_starnet2(*, returncode: int = 0, write_output: bool = True):
    """A stand-in for the binary: copies the input TIFF to the output path."""

    def run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if write_output and returncode == 0:
            source = cv2.imread(cmd[cmd.index("-i") + 1], cv2.IMREAD_COLOR)
            cv2.imwrite(cmd[cmd.index("-o") + 1], source)
        return subprocess.CompletedProcess(
            cmd, returncode, stdout="", stderr="boom" if returncode else ""
        )

    return run


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
