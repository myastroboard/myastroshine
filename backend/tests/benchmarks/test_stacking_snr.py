"""SNR-improvement acceptance criterion: stacking should reduce noise by ~sqrt(N).

Runs the real ``IntegrationService`` pipeline (register -> normalise -> reject ->
weighted combine) on synthetic star fields with a known signal and known,
controlled Gaussian noise, and checks the measured noise reduction against the
theoretical ``sqrt(effective N)``.

Opt-in and excluded from the default run - a wall-clock / statistical check like
this doesn't belong in the suite gating every push:

    RUN_BENCHMARKS=1 pytest tests/benchmarks --no-cov -v
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.services.integration import IntegrationService
from app.services.storage import StorageService
from app.utils.linear_ingest import LinearFrame

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BENCHMARKS") != "1",
    reason="opt-in: set RUN_BENCHMARKS=1 (see this file's module docstring)",
)

FRAME_COUNT = 16
NOISE_STD = 0.02
TOLERANCE = 0.20  # vs the theoretical sqrt(N) - float16 store + finite-sample noise


def _truth(height: int, width: int, seed: int) -> np.ndarray:
    """A noise-free frame: a smooth sky plus ~60 stars for the matcher to lock onto."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:height, 0:width]
    sky = 0.15 + 0.05 * (x / width + y / height)
    signal = np.stack([sky, sky * 0.95, sky * 0.9], axis=-1).astype(np.float32)
    for _ in range(60):
        cy, cx = int(rng.integers(20, height - 20)), int(rng.integers(20, width - 20))
        cv2.circle(signal, (cx, cy), int(rng.integers(1, 3)), (0.8, 0.8, 0.8), -1)
    return signal


def _residual_std(observed: np.ndarray, truth: np.ndarray) -> float:
    inner = (slice(20, -20), slice(20, -20))
    return float(np.std(observed[inner].astype(np.float64) - truth[inner]))


def test_integration_reduces_noise_by_sqrt_n() -> None:
    truth = _truth(140, 180, seed=1)
    rng = np.random.default_rng(7)
    root = Path(tempfile.mkdtemp())
    storage = StorageService(root=root)

    single_noise = []
    for i in range(FRAME_COUNT):
        noisy = np.clip(truth + rng.normal(0, NOISE_STD, truth.shape), 0, 1).astype(np.float32)
        single_noise.append(_residual_std(noisy, truth))
        storage.save_linear_frame("snr", i, LinearFrame(data=noisy, source_bit_depth=16))

    result = IntegrationService(storage).integrate(
        "snr",
        list(range(FRAME_COUNT)),
        transform="similarity",
        combination="average",
        rejection="winsorized_sigma",
        weighting="none",
    )

    empirical = float(np.mean(single_noise)) / _residual_std(result.composite, truth)
    theoretical = result.effective_frames**0.5

    assert empirical == pytest.approx(theoretical, rel=TOLERANCE), (
        f"stacking {FRAME_COUNT} frames reduced noise {empirical:.2f}x, "
        f"theory predicts {theoretical:.2f}x"
    )
