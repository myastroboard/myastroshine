"""Golden-image regression tests for the single-image enhancement pipeline.

Runs a small, fully deterministic synthetic frame through the real
``ImageProcessingService`` for the default parameters and each built-in
preset, and diffs the output against a checked-in reference PNG. Unlike
``tests/services/test_image_processing.py`` (one stage, one property at a
time), this catches a regression that runs cleanly with no exception but
quietly changes what the *whole* pipeline produces on a realistic parameter
set - the shape of the 0.4.1 bug where the colour-calibration gain landed
within 0.3% of 1.0 and silently did nothing, caught only by side-by-side manual
testing.

A deliberate pipeline change updates the references instead of fighting the
test:

    UPDATE_GOLDEN=1 pytest tests/regression/test_pipeline_golden.py -v
"""

from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.models import ProcessingParameters
from app.services.image_processing import ImageProcessingService
from app.services.preset import _DEFAULTS

GOLDEN_DIR = Path(__file__).parent / "golden"
UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"
#: of 255 - tight enough to catch a real behaviour change, loose enough to
#: tolerate cross-platform OpenCV rounding jitter (SIMD backend, library patch
#: version) in filters like GaussianBlur/bilateralFilter.
MAX_MEAN_ABS_DIFF = 1.5


def _synthetic_photo(height: int = 160, width: int = 220, seed: int = 42) -> np.ndarray:
    """A small deterministic BGR uint8 frame: a warm-cast sky gradient, a soft
    nebula-like blob, and a field of point stars - enough structure to
    exercise white balance, gradient reduction, tone/contrast, and star
    reduction meaningfully."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    sky = 0.12 + 0.06 * (x / width) + 0.03 * (y / height)
    image = np.stack([sky * 0.85, sky * 0.9, sky * 1.05], axis=-1)  # BGR, warm cast

    blob = np.zeros((height, width), dtype=np.float32)
    cv2.circle(blob, (width * 3 // 5, height * 2 // 5), min(height, width) // 4, 1.0, -1)
    blob = cv2.GaussianBlur(blob, (0, 0), sigmaX=min(height, width) / 8)
    image += blob[:, :, np.newaxis] * np.array([0.05, 0.15, 0.08], dtype=np.float32)

    for _ in range(40):
        cx, cy = int(rng.integers(10, width - 10)), int(rng.integers(10, height - 10))
        radius = int(rng.integers(1, 3))
        brightness = float(rng.uniform(0.5, 1.0))
        cv2.circle(image, (cx, cy), radius, (brightness, brightness, brightness), -1)

    return np.clip(image * 255.0, 0, 255).astype(np.uint8)


@pytest.fixture(scope="module")
def photo() -> np.ndarray:
    return _synthetic_photo()


def _preset_cases() -> list[tuple[str, ProcessingParameters]]:
    """Default parameters plus every built-in preset (``PresetService``'s own
    ``_DEFAULTS`` - importing it keeps this test in sync automatically, rather
    than duplicating the parameter values here)."""
    cases = [("default", ProcessingParameters())]
    cases.extend(
        (spec["preset_id"], ProcessingParameters(**spec["parameters"])) for spec in _DEFAULTS
    )
    return cases


_CASES = _preset_cases()


def _compare_or_update(name: str, actual: np.ndarray) -> None:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    path = GOLDEN_DIR / f"{name}.png"
    if UPDATE or not path.exists():
        cv2.imwrite(str(path), actual)
        return

    reference = cv2.imread(str(path))
    assert reference is not None, f"could not read golden reference {path}"
    assert reference.shape == actual.shape, (
        f"{name}: output shape changed ({reference.shape} -> {actual.shape}) - "
        "rerun with UPDATE_GOLDEN=1 if that's intentional"
    )
    mean_abs_diff = float(np.abs(actual.astype(np.int16) - reference.astype(np.int16)).mean())
    assert mean_abs_diff <= MAX_MEAN_ABS_DIFF, (
        f"{name}: pipeline output drifted from the golden reference "
        f"(mean abs diff {mean_abs_diff:.3f} > {MAX_MEAN_ABS_DIFF}) - "
        "a real change? rerun with UPDATE_GOLDEN=1 to accept it"
    )


@pytest.mark.parametrize("case", _CASES, ids=[case[0] for case in _CASES])
def test_pipeline_golden(photo: np.ndarray, case: tuple[str, ProcessingParameters]) -> None:
    name, params = case
    result = ImageProcessingService().apply_parameters(photo, params)
    _compare_or_update(f"pipeline_{name}", result)
