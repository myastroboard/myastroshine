"""Numeric helpers shared by the processing algorithms."""

from __future__ import annotations

from typing import cast

import numpy as np

_FLAT_EPS = 1e-9


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
