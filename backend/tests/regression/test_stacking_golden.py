"""Golden-image regression test for the stacking integration pipeline.

Same rationale as ``test_pipeline_golden.py``, for
``IntegrationService.integrate()`` (register -> align -> combine) instead of
the single-image enhancement pipeline. A small, fully deterministic synthetic
frame set (seeded noise, ``workers=1`` for a deterministic combine order) is
stacked and the composite diffed against a checked-in reference.

    UPDATE_GOLDEN=1 pytest tests/regression/test_stacking_golden.py -v
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import cv2
import numpy as np

from app.services.integration import IntegrationService
from app.services.storage import StorageService
from app.utils.linear_ingest import LinearFrame

GOLDEN_DIR = Path(__file__).parent / "golden"
UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"
#: the composite is linear float32 in ~[0, 1] - much tighter than the 8-bit
#: pipeline's tolerance since there's no display-range quantisation here.
MAX_MEAN_ABS_DIFF = 2e-3

FRAME_COUNT = 6
NOISE_STD = 0.02


def _truth(height: int, width: int, seed: int) -> np.ndarray:
    """A noise-free frame: a smooth sky plus stars for the matcher to lock
    onto - the same construction ``tests/benchmarks/test_stacking_snr.py``
    uses, at a smaller size (this checks pipeline stability, not SNR gain)."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:height, 0:width]
    sky = 0.15 + 0.05 * (x / width + y / height)
    signal = np.stack([sky, sky * 0.95, sky * 0.9], axis=-1).astype(np.float32)
    for _ in range(60):
        cy, cx = int(rng.integers(20, height - 20)), int(rng.integers(20, width - 20))
        cv2.circle(signal, (cx, cy), int(rng.integers(1, 3)), (0.8, 0.8, 0.8), -1)
    return signal


def test_stacking_golden() -> None:
    truth = _truth(140, 180, seed=3)
    rng = np.random.default_rng(11)
    storage = StorageService(root=Path(tempfile.mkdtemp()))

    for i in range(FRAME_COUNT):
        noisy = np.clip(truth + rng.normal(0, NOISE_STD, truth.shape), 0, 1).astype(np.float32)
        storage.save_linear_frame("golden", i, LinearFrame(data=noisy, source_bit_depth=16))

    result = IntegrationService(storage, workers=1).integrate(
        "golden",
        list(range(FRAME_COUNT)),
        transform="similarity",
        combination="average",
        rejection="winsorized_sigma",
        weighting="none",
    )

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    path = GOLDEN_DIR / "stack_composite.npz"
    if UPDATE or not path.exists():
        np.savez_compressed(path, composite=result.composite)
        return

    reference = np.load(path)["composite"]
    assert reference.shape == result.composite.shape, (
        f"stack composite shape changed ({reference.shape} -> {result.composite.shape}) - "
        "rerun with UPDATE_GOLDEN=1 if that's intentional"
    )
    mean_abs_diff = float(np.abs(result.composite - reference).mean())
    assert mean_abs_diff <= MAX_MEAN_ABS_DIFF, (
        f"stacking composite drifted from the golden reference "
        f"(mean abs diff {mean_abs_diff:.5f} > {MAX_MEAN_ABS_DIFF}) - "
        "a real change? rerun with UPDATE_GOLDEN=1 to accept it"
    )
