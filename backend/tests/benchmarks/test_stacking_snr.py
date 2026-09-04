"""SNR-improvement acceptance criterion (release-hardening backlog #4): stacking
should improve SNR by ~sqrt(N).

``CombinationService.estimate_snr_improvement`` is literally ``sqrt(N)`` (see
app/services/combination.py) - the existing unit test for it
(tests/services/test_combination.py) only confirms that formula matches its
own definition, which is a tautology. This test instead measures the *actual*
noise reduction ``combine(..., method="mean")`` produces on synthetic frames
with known, controlled noise, and checks it against the theoretical claim -
"mean" is the method the docs (docs/ALGORITHMS.md) call optimal at exactly
sqrt(N); median/sigma_clip trade a bit of that for robustness and are out of
scope here since ``estimate_snr_improvement`` doesn't vary by method either.

Opt-in and excluded from the default run - see test_processing_speed.py's
module docstring for why (same reasoning: a wall-clock/statistical check like
this doesn't belong in the suite gating every push):

    RUN_BENCHMARKS=1 pytest tests/benchmarks --no-cov -v
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from app.services.combination import CombinationService

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BENCHMARKS") != "1",
    reason="opt-in: set RUN_BENCHMARKS=1 (see this file's module docstring)",
)

FRAME_COUNT = 16
NOISE_STD = 20.0
TOLERANCE = 0.15  # vs the theoretical sqrt(N) - quantization + finite-sample noise


def _smooth_signal(height: int, width: int) -> np.ndarray:
    """A noise-free "true" frame: smooth gradients only, no point sources -
    stars would occasionally clip at 255 under added noise and bias a
    residual-std measurement, which isn't what this test is checking."""
    x = np.linspace(90, 150, width)
    y = np.linspace(100, 160, height)
    base = (x[np.newaxis, :] + y[:, np.newaxis]) / 2
    return np.stack([base, base * 0.9 + 10, base * 0.8 + 20], axis=-1)


def _noisy_frames(signal: np.ndarray, count: int, *, seed: int) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    frames = []
    for _ in range(count):
        noisy = signal + rng.normal(0.0, NOISE_STD, signal.shape)
        frames.append(np.clip(noisy, 0, 255).astype(np.uint8))
    return frames


def _residual_std(observed: np.ndarray, signal: np.ndarray) -> float:
    """Std of (observed - ground truth) - our noise proxy, since we control
    the "true" signal exactly (real frames never let you measure this)."""
    return float(np.std(observed.astype(np.float64) - signal))


def test_mean_combination_reduces_noise_by_sqrt_n() -> None:
    signal = _smooth_signal(96, 128)
    frames = _noisy_frames(signal, FRAME_COUNT, seed=7)

    single_frame_noise = float(np.mean([_residual_std(f, signal) for f in frames]))
    stacked = CombinationService().combine(frames, method="mean")
    stacked_noise = _residual_std(stacked, signal)

    empirical_improvement = single_frame_noise / stacked_noise
    theoretical_improvement = CombinationService().estimate_snr_improvement(FRAME_COUNT)

    assert empirical_improvement == pytest.approx(theoretical_improvement, rel=TOLERANCE), (
        f"stacking {FRAME_COUNT} frames reduced noise {empirical_improvement:.2f}x, "
        f"theory predicts {theoretical_improvement:.2f}x (sqrt({FRAME_COUNT}))"
    )
