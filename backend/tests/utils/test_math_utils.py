"""Numeric helpers."""

from __future__ import annotations

import numpy as np

from app.utils.math_utils import kelvin_to_rgb_gain, normalize_01, tint_to_rgb_gain, to_uint8


def test_normalize_01_maps_to_unit_range() -> None:
    """min -> 0, max -> 1."""
    out = normalize_01(np.array([10, 20, 30], dtype=np.float32))
    assert out.min() == 0.0
    assert out.max() == 1.0


def test_normalize_01_flat_array_is_zeros() -> None:
    """A constant array cannot be stretched and maps to zeros."""
    out = normalize_01(np.full((4, 4), 7.0, dtype=np.float32))
    assert np.all(out == 0.0)


def test_to_uint8_clips_out_of_range() -> None:
    """Values outside 0-255 are clamped, not wrapped."""
    out = to_uint8(np.array([-5.0, 0.0, 128.0, 260.0]))
    assert out.tolist() == [0, 0, 128, 255]
    assert out.dtype == np.uint8


def test_kelvin_gain_neutral_at_6500() -> None:
    """6500K is the neutral point."""
    assert kelvin_to_rgb_gain(6500) == (1.0, 1.0, 1.0)


def test_kelvin_gain_direction() -> None:
    """Warm lowers blue; cool raises it."""
    assert kelvin_to_rgb_gain(3000)[2] < 1.0
    assert kelvin_to_rgb_gain(8000)[2] > 1.0


def test_tint_gain_neutral_at_zero() -> None:
    """tint 0 is neutral."""
    assert tint_to_rgb_gain(0) == (1.0, 1.0, 1.0)
