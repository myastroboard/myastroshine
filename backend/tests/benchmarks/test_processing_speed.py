"""Performance acceptance criteria (release-hardening backlog #4, see
initial_plan/10_IMPLEMENTATION_ROADMAP.md "Success Metrics"):

    full-res enhance < 5s; slider (preview) response < 500ms

Opt-in and excluded from the default ``pytest`` run: wall-clock budgets are
inherently sensitive to the machine running them (a busy CI runner can be
several times slower than a quiet laptop) and to coverage instrumentation
(``pytest-cov``, on by default via ``addopts`` - it measurably slows CPython
down), so folding them into the suite that gates every push/PR would trade a
green check for periodic false failures. Run explicitly when you want the
signal, without coverage skewing the timing:

    RUN_BENCHMARKS=1 pytest tests/benchmarks --no-cov -v

See CONTRIBUTING.md "Backend checks" and .github/workflows/benchmarks.yml.
"""

from __future__ import annotations

import os
import time

import numpy as np
import pytest

from app.models import ProcessingParameters
from app.services.image_processing import ImageProcessingService

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BENCHMARKS") != "1",
    reason="opt-in: set RUN_BENCHMARKS=1 (see this file's module docstring)",
)

FULL_RES_BUDGET_SECONDS = 5.0
PREVIEW_BUDGET_SECONDS = 0.5


def _typical_edit() -> ProcessingParameters:
    """A realistic multi-slider edit - every pipeline stage does real work,
    unlike the all-defaults case ``apply_parameters`` short-circuits."""
    return ProcessingParameters(
        contrast=1.4,
        brightness=0.15,
        saturation=1.3,
        highlights=-0.3,
        shadows=0.4,
        clarity=0.5,
        vibrance=1.2,
        denoise=50,
        star_reduction=40,
        sharpness=1.3,
        temperature=7200,
        tint=8,
    )


def _time_enhance(image: np.ndarray) -> float:
    service = ImageProcessingService()
    params = _typical_edit()
    start = time.perf_counter()
    service.apply_parameters(image, params, None)
    return time.perf_counter() - start


def test_full_res_enhance_completes_within_budget(full_res_image: np.ndarray) -> None:
    elapsed = _time_enhance(full_res_image)
    height, width = full_res_image.shape[:2]
    assert elapsed < FULL_RES_BUDGET_SECONDS, (
        f"full-res enhance ({width}x{height}) took {elapsed:.2f}s, "
        f"budget is {FULL_RES_BUDGET_SECONDS}s"
    )


def test_preview_slider_response_completes_within_budget(preview_image: np.ndarray) -> None:
    elapsed = _time_enhance(preview_image)
    height, width = preview_image.shape[:2]
    assert elapsed < PREVIEW_BUDGET_SECONDS, (
        f"preview reprocess ({width}x{height}) took {elapsed * 1000:.0f}ms, "
        f"budget is {PREVIEW_BUDGET_SECONDS * 1000:.0f}ms"
    )
