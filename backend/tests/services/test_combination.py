"""CombinationService: median / mean / sigma-clip stacking."""

from __future__ import annotations

import numpy as np
import pytest

from app.exceptions import InvalidParameterError
from app.services.combination import CombinationService


@pytest.fixture
def frames() -> list[np.ndarray]:
    rng = np.random.default_rng(11)
    base = np.full((40, 40, 3), 100, dtype=np.int16)
    return [
        np.clip(base + rng.integers(-6, 7, base.shape), 0, 255).astype(np.uint8) for _ in range(8)
    ]


def test_median_is_robust_to_one_bad_frame(frames: list[np.ndarray]) -> None:
    """A wildly wrong frame barely moves the median composite."""
    good = CombinationService().combine(frames, "median")

    frames[3][:] = 250
    with_outlier = CombinationService().combine(frames, "median")

    assert np.mean(np.abs(good.astype(int) - with_outlier.astype(int))) < 5


def test_mean_reduces_noise(frames: list[np.ndarray]) -> None:
    """The mean composite has lower variance than a single frame."""
    combined = CombinationService().combine(frames, "mean")
    assert float(np.var(combined)) < float(np.var(frames[0]))


def test_sigma_clip_runs_and_stays_in_range(frames: list[np.ndarray]) -> None:
    combined = CombinationService().combine(frames, "sigma_clip")
    assert combined.shape == frames[0].shape
    assert combined.dtype == np.uint8


def test_reject_mask_excludes_flagged_samples(frames: list[np.ndarray]) -> None:
    """A masked spike does not reach the composite."""
    frames[2][20, 20] = 255
    mask = np.zeros((len(frames), *frames[0].shape), dtype=bool)
    mask[2, 20, 20] = True

    combined = CombinationService().combine(frames, "median", reject_mask=mask)
    assert int(combined[20, 20].max()) < 130


def test_unknown_method_raises(frames: list[np.ndarray]) -> None:
    with pytest.raises(InvalidParameterError):
        CombinationService().combine(frames, "average")


def test_empty_raises() -> None:
    with pytest.raises(InvalidParameterError):
        CombinationService().combine([], "median")


def test_snr_improvement_tracks_sqrt_n() -> None:
    assert CombinationService().estimate_snr_improvement(16) == pytest.approx(4.0)
