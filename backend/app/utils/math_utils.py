"""Numeric helpers shared by the processing algorithms."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import cast

import numpy as np

_FLAT_EPS = 1e-9

# Fritsch-Carlson monotone-cubic constants (see _fritsch_carlson_tangents).
_MIN_POINTS_FOR_INTERIOR_TANGENTS = 2
_MONOTONE_MAGNITUDE_LIMIT = 9.0


def normalize_01(array: np.ndarray) -> np.ndarray:
    """Scale an array to the 0-1 range (min-max), as float32.

    A flat array (min == max) maps to all zeros.
    """
    arr = array.astype(np.float32)
    lo = float(arr.min())
    hi = float(arr.max())
    if hi - lo < _FLAT_EPS:
        return np.zeros_like(arr)
    return cast("np.ndarray", (arr - lo) / (hi - lo))


def to_uint8(array: np.ndarray) -> np.ndarray:
    """Clip to 0-255 and cast to ``uint8``."""
    return cast("np.ndarray", np.clip(array, 0, 255).astype(np.uint8))


def kelvin_to_rgb_gain(temperature: int) -> tuple[float, float, float]:
    """Map a colour temperature in Kelvin to per-channel RGB multipliers.

    6500K is neutral ``(1, 1, 1)``. Warmer (lower K) lifts red and drops blue;
    cooler (higher K) does the opposite. The response is deliberately gentle -
    the full 2000-8000K range stays within +/- 30 percent per channel.
    """
    t = (temperature - 6500) / 2000.0  # roughly -2.25 .. +0.75
    if t >= 0:
        # cooler: boost blue
        return (1.0, 1.0, 1.0 + t * 0.3)
    warm = abs(t)
    # warmer: pull down blue and, a little, green
    return (1.0, 1.0 - warm * 0.15, 1.0 - warm * 0.3)


def tint_to_rgb_gain(tint: int) -> tuple[float, float, float]:
    """Map a tint value (-50 green .. +50 magenta) to RGB multipliers."""
    t = tint / 50.0
    if t >= 0:
        return (1.0 + t * 0.1, 1.0, 1.0 + t * 0.1)  # magenta
    return (1.0, 1.0 + abs(t) * 0.1, 1.0)  # green


def _fritsch_carlson_tangents(xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Per-point tangents for a monotone cubic Hermite spline through (xs, ys).

    Standard averaged-secant tangents, then the Fritsch-Carlson correction so
    the spline can never overshoot past a control point's y-value inside its
    neighbouring segments - important for a tone curve, where an overshoot
    would locally crush shadows or blow out highlights the user never asked
    for. ``xs`` must be strictly increasing.
    """
    n = len(xs)
    deltas = (ys[1:] - ys[:-1]) / (xs[1:] - xs[:-1])
    tangents = np.zeros(n)
    tangents[0] = deltas[0]
    tangents[-1] = deltas[-1]
    if n > _MIN_POINTS_FOR_INTERIOR_TANGENTS:
        tangents[1:-1] = (deltas[:-1] + deltas[1:]) / 2.0

    for i in range(n - 1):
        if deltas[i] == 0:
            tangents[i] = 0.0
            tangents[i + 1] = 0.0
            continue
        alpha = max(tangents[i] / deltas[i], 0.0)
        beta = max(tangents[i + 1] / deltas[i], 0.0)
        tangents[i] = alpha * deltas[i]
        tangents[i + 1] = beta * deltas[i]
        magnitude = alpha * alpha + beta * beta
        if magnitude > _MONOTONE_MAGNITUDE_LIMIT:
            scale = 3.0 / math.sqrt(magnitude)
            tangents[i] = scale * alpha * deltas[i]
            tangents[i + 1] = scale * beta * deltas[i]

    return tangents


def curve_points_to_lut(points: Sequence[tuple[int, int]]) -> np.ndarray:
    """Build a 256-entry ``uint8`` lookup table from tone-curve control points.

    ``points`` are ``(input, output)`` pairs, both 0-255, sorted by input,
    spanning the full range (first at x=0, last at x=255) - the caller
    validates this shape (see ``ProcessingParameters.curve_points``); an empty
    sequence returns the identity LUT. Interpolated with a monotone cubic
    Hermite spline rather than a plain polyline, so a few dragged points make
    a smooth curve instead of visible straight-line kinks.
    """
    if not points:
        return np.arange(256, dtype=np.uint8)

    xs = np.array([p[0] for p in points], dtype=np.float64)
    ys = np.array([p[1] for p in points], dtype=np.float64)
    tangents = _fritsch_carlson_tangents(xs, ys)

    sample_x = np.arange(256, dtype=np.float64)
    segment = np.clip(np.searchsorted(xs, sample_x, side="right") - 1, 0, len(xs) - 2)
    x0, x1 = xs[segment], xs[segment + 1]
    y0, y1 = ys[segment], ys[segment + 1]
    m0, m1 = tangents[segment], tangents[segment + 1]

    h = x1 - x0
    t = (sample_x - x0) / h
    t2 = t * t
    t3 = t2 * t
    h00 = 2 * t3 - 3 * t2 + 1
    h10 = t3 - 2 * t2 + t
    h01 = -2 * t3 + 3 * t2
    h11 = t3 - t2
    values = h00 * y0 + h10 * h * m0 + h01 * y1 + h11 * h * m1
    return cast("np.ndarray", np.clip(values, 0, 255).astype(np.uint8))
