"""NormalizationService: equalising sky background across frames."""

from __future__ import annotations

import numpy as np

from app.services.normalization import NormalizationService


def _frame(background: int) -> np.ndarray:
    image = np.full((100, 100, 3), background, dtype=np.uint8)
    image[45:55, 45:55] = 220  # a "star" the normalisation must not touch much
    return image


def test_backgrounds_converge() -> None:
    """Frames at different background levels come out near-equal."""
    frames = [_frame(60), _frame(90), _frame(75)]
    out = NormalizationService().normalize_backgrounds(frames)

    borders = [float(np.median(f[:32, :])) for f in out]
    assert max(borders) - min(borders) <= 2


def test_uses_explicit_reference() -> None:
    out = NormalizationService().normalize_backgrounds([_frame(50)], reference_bg=100.0)
    assert abs(float(np.median(out[0][:32, :])) - 100.0) <= 2


def test_empty_input() -> None:
    assert NormalizationService().normalize_backgrounds([]) == []


def test_output_stays_uint8_in_range() -> None:
    out = NormalizationService().normalize_backgrounds([_frame(10), _frame(240)])
    for frame in out:
        assert frame.dtype == np.uint8
        assert frame.min() >= 0
        assert frame.max() <= 255
