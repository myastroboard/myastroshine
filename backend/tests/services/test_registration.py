"""RegistrationService: frame alignment via feature matching."""

from __future__ import annotations

import numpy as np
import pytest

from app.services.registration import RegistrationService
from tests.support import translate


@pytest.mark.parametrize("detector", ["orb", "sift"])
def test_aligns_a_shifted_frame(star_field: np.ndarray, detector: str) -> None:
    """A frame translated by (7, -5) is warped back close to the reference."""
    shifted = translate(star_field, 7, -5)
    result = RegistrationService(detector).register([star_field, shifted])

    assert result.aligned_flags == [True, True]
    ref = star_field[12:-12, 12:-12].astype(int)
    got = result.aligned[1][12:-12, 12:-12].astype(int)
    before = np.mean(np.abs(ref - shifted[12:-12, 12:-12].astype(int)))
    after = np.mean(np.abs(ref - got))
    assert after < before


def test_reference_frame_is_untouched(star_field: np.ndarray) -> None:
    result = RegistrationService("orb").register([star_field, translate(star_field, 3, 3)])
    assert np.array_equal(result.aligned[0], star_field)


def test_featureless_frame_is_flagged_not_aligned() -> None:
    """A flat frame cannot be matched; it is returned unchanged and flagged."""
    flat = np.full((80, 80, 3), 30, dtype=np.uint8)
    other = flat.copy()
    other[40:45, 40:45] = 200
    result = RegistrationService("orb").register([flat, other])

    assert result.aligned_flags[1] is False
    assert np.array_equal(result.aligned[1], other)
    assert 0.0 <= result.success_rate <= 1.0


def test_single_frame_is_a_no_op(star_field: np.ndarray) -> None:
    result = RegistrationService("orb").register([star_field])
    assert result.aligned == [star_field]
