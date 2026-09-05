"""Numeric helpers."""

from __future__ import annotations

import numpy as np

from app.utils.math_utils import (
    curve_points_to_lut,
    kelvin_to_rgb_gain,
    normalize_01,
    tint_to_rgb_gain,
    to_uint8,
)


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


def test_curve_lut_empty_is_identity() -> None:
    """No control points -> every level maps to itself."""
    lut = curve_points_to_lut([])
    assert lut.tolist() == list(range(256))


def test_curve_lut_two_points_is_linear() -> None:
    """A single segment has no interior tangent to reconcile - plain linear."""
    lut = curve_points_to_lut([(0, 0), (255, 128)])
    assert lut[0] == 0
    assert lut[255] == 128
    assert lut[128] == round(128 * 128 / 255)


def test_curve_lut_flips_dark_and_light() -> None:
    """An inverted curve maps low input to high output and vice versa."""
    lut = curve_points_to_lut([(0, 255), (255, 0)])
    assert lut[0] == 255
    assert lut[255] == 0


def test_curve_lut_passes_through_every_control_point() -> None:
    """The interpolated curve hits each control point's exact value."""
    points = [(0, 10), (64, 40), (160, 220), (255, 245)]
    lut = curve_points_to_lut(points)
    for x, y in points:
        assert lut[x] == y


def test_curve_lut_is_monotone_for_an_s_curve() -> None:
    """A classic contrast S-curve never dips - output never decreases as input rises."""
    points = [(0, 0), (64, 40), (192, 215), (255, 255)]
    lut = curve_points_to_lut(points)
    diffs = np.diff(lut.astype(np.int32))
    assert np.all(diffs >= 0)


def test_curve_lut_stays_in_bounds() -> None:
    """Even a curve with a steep midtone jump never overshoots past 0-255."""
    points = [(0, 0), (120, 250), (135, 5), (255, 255)]
    lut = curve_points_to_lut(points)
    assert lut.min() >= 0
    assert lut.max() <= 255
