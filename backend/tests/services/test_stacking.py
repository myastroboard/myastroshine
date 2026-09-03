"""Stacking pipeline tests (registration, normalization, cosmic rays,
combination). Filled in during Sprints 6-7."""

from __future__ import annotations

import pytest

_NOT_YET = pytest.mark.skip(reason="Stacking services not implemented yet (Sprint 6/7)")


@_NOT_YET
def test_registration_aligns_shifted_frame_within_one_pixel() -> None:
    """A synthetically shifted frame is realigned to < 1px error."""


@_NOT_YET
def test_combine_median_is_robust_to_a_single_outlier_frame() -> None:
    """One bad frame does not corrupt the median composite."""


def test_snr_improvement_tracks_sqrt_n() -> None:
    """estimate_snr_improvement(N) == sqrt(N)."""
    from app.services.combination import CombinationService

    assert CombinationService().estimate_snr_improvement(16) == pytest.approx(4.0)
