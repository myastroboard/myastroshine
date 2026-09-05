"""Star detection alone must stay fast enough for the mask-preview endpoint.

``POST /api/star-mask/{session_id}`` runs detection standalone (no full
pipeline) on every toggle/slider change while the mask overlay is on, so it
needs its own budget check independent of ``test_processing_speed.py``'s
full-pipeline numbers. See that file's docstring for why this suite is opt-in.
"""

from __future__ import annotations

import os
import time

import numpy as np
import pytest

from app.services.star_detection import StarDetectionService

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BENCHMARKS") != "1",
    reason="opt-in: set RUN_BENCHMARKS=1 (see this file's module docstring)",
)

PREVIEW_BUDGET_SECONDS = 0.5


def test_preview_detection_completes_within_budget(preview_image: np.ndarray) -> None:
    detector = StarDetectionService()
    start = time.perf_counter()
    detector.detect(preview_image, sensitivity=50, max_size=30)
    elapsed = time.perf_counter() - start

    assert elapsed < PREVIEW_BUDGET_SECONDS, (
        f"star detection on the preview image took {elapsed * 1000:.0f}ms, "
        f"budget is {PREVIEW_BUDGET_SECONDS * 1000:.0f}ms"
    )
