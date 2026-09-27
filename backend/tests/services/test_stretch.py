"""The adaptive, colour-preserving stretch of a linear composite."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.services.stretch import _curve, _solve_family, adaptive_stretch


def _scene(size: int = 400, seed: int = 0, galaxy: float = 0.02) -> np.ndarray:
    """Linear RGB: sky noise around 0, a bright elongated galaxy, a few stars."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    r2 = ((xx - size / 2) / (size / 4)) ** 2 + ((yy - size / 2) / (size / 10)) ** 2
    body = galaxy * np.exp(-r2) + 0.4 * galaxy * np.exp(-r2 * 60)  # disc + bright core
    rgb = np.stack([body * 1.2, body, body * 0.7], axis=-1)
    for _ in range(40):
        x, y = rng.integers(5, size - 5, 2)
        rgb[y, x] += (0.1, 0.1, 0.25)  # blue-ish stars
    rgb = cv2.GaussianBlur(rgb, (0, 0), 1.0)
    return (rgb + rng.normal(0, 0.0003, rgb.shape)).astype(np.float32)


def test_output_is_bgr_float_in_range() -> None:
    out = adaptive_stretch(_scene(), 0.1)
    assert out.dtype == np.float32
    assert out.shape == (400, 400, 3)
    assert float(out.min()) >= 0.0
    assert float(out.max()) <= 1.0


def test_sky_lands_near_the_target_background() -> None:
    """A higher target lifts the sky; the sky sits near (a bit below) the target,
    since the black point is set a few noise sigma under it."""
    scene = _scene()
    corner = (slice(0, 60), slice(0, 60))
    low = float(adaptive_stretch(scene, 0.05)[corner].mean())
    high = float(adaptive_stretch(scene, 0.2)[corner].mean())
    assert 0.01 < low < 0.08
    assert high > low * 2


def test_colour_ratios_survive_the_stretch() -> None:
    """The galaxy keeps its red-over-blue colour instead of being pushed toward
    grey the way three identical per-channel curves would."""
    out = adaptive_stretch(_scene(), 0.1)
    b, _, r = out[200, 150]
    assert r > b * 1.3


def test_bright_core_is_not_clipped_flat() -> None:
    """The core keeps structure: its centre is brighter than its shoulder and
    stays below full white."""
    out = adaptive_stretch(_scene(galaxy=0.3), 0.1)
    luma = out.mean(axis=2)
    assert luma[200, 200] > luma[200, 185]
    assert luma[200, 200] < 0.999


def test_overflowing_colour_is_desaturated_not_darkened() -> None:
    """A saturated pixel that would exceed 1 keeps its brightness: the overflow
    is traded for saturation, so no dark ring forms round a bright blue star."""
    scene = _scene()
    scene[100:104, 100:104] = (0.02, 0.05, 1.5)
    out = adaptive_stretch(scene, 0.15)
    patch = out[101, 101]
    assert float(patch.max()) <= 1.0
    assert float(patch.mean()) > 0.5


def test_clipped_source_pixels_are_faded_to_neutral() -> None:
    """Where the source was near saturation its colour is unreliable, so the
    stretched pixel is neutral rather than a coloured ring."""
    scene = _scene()
    scene[300:310, 300:310] = (0.2, 0.6, 1.0)
    source_peak = np.zeros(scene.shape[:2], dtype=np.float32)
    source_peak[300:310, 300:310] = 1.0

    out = adaptive_stretch(scene, 0.1, source_peak=source_peak)

    b, g, r = out[305, 305]
    assert max(b, g, r) - min(b, g, r) < 0.05


def test_mono_like_data_stays_grey() -> None:
    grey = np.repeat(_scene()[..., 1:2], 3, axis=2)
    out = adaptive_stretch(grey, 0.1)
    assert float(np.abs(out[..., 0] - out[..., 2]).max()) < 1e-4


@pytest.mark.parametrize(
    ("x_sky", "x_obj"), [(0.01, 0.05), (0.01, 0.4), (0.002, 0.1), (0.005, 0.3)]
)
def test_family_solution_maps_the_object_to_its_target(x_sky: float, x_obj: float) -> None:
    """Whatever the sky/object contrast, the solved curve lands the object level
    on the object target (when the family can reach it)."""
    from app.services.stretch import _OBJECT_TARGET

    white_floor = min(max(x_obj * 1.2, x_sky * 4.0), 1.0)
    family = _solve_family(x_sky, x_obj, 0.1, white_floor)
    reached = float(_curve(np.array(x_obj), family, x_sky, 0.1, white_floor))
    assert -1.0 < family < 1.0
    assert reached == pytest.approx(_OBJECT_TARGET, abs=0.01)


def test_curve_maps_the_sky_to_the_target_at_every_family_value() -> None:
    for family in (-1.0, -0.4, 0.0, 0.5, 1.0):
        assert float(_curve(np.array(0.01), family, 0.01, 0.12, 0.3)) == pytest.approx(0.12, 1e-3)


def test_family_solution_clamps_at_both_ends() -> None:
    """An object that cannot reach the target even with the white point fully
    lowered takes the low end; one far too bright takes the high end."""
    assert _solve_family(0.01, 0.0101, 0.1, 0.02) == -1.0
    assert _solve_family(1e-6, 1.0, 0.1, 1.0) == 1.0
