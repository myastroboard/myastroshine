"""Post-stack cleanup: crop the wedge (baked), then the non-destructive
background / colour / stretch pre-stage the editor drives."""

from __future__ import annotations

import numpy as np

from app.models import StackParameters
from app.services.post_stack import (
    apply_post_stack,
    calibrate_colour,
    extract_background,
    render_stack_base,
)


def _linear_sky(height: int, width: int, seed: int = 1) -> np.ndarray:
    """A linear composite: faint sky + a light-pollution gradient + a red cast."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    gradient = 0.004 + 0.010 * (xx / width) + 0.006 * (yy / height)
    rgb = np.stack([gradient * 1.15, gradient, gradient * 0.9], axis=-1)
    return rgb + rng.normal(0, 0.0004, (height, width, 3)).astype(np.float32)


# -- 1. wedge crop (the only step baked into composite.npy) ----------------


def test_crop_removes_the_low_coverage_wedge() -> None:
    comp = _linear_sky(300, 400)
    coverage = np.full((300, 400), 80, dtype=np.int32)
    coverage[:30] = 4  # a rotation wedge on each edge
    coverage[-30:] = 4
    coverage[:, :50] = 4
    coverage[:, -50:] = 4

    out, report = apply_post_stack(comp, coverage)

    assert report.cropped is not None
    top, left, h, w = report.cropped
    assert top >= 25 and left >= 45  # the wedge rows/cols were trimmed
    assert out.shape[:2] == (h, w)


def test_full_coverage_is_not_cropped() -> None:
    comp = _linear_sky(200, 200)
    coverage = np.full((200, 200), 50, dtype=np.int32)
    out, report = apply_post_stack(comp, coverage)
    assert report.cropped is None
    assert out.shape[:2] == (200, 200)


def test_apply_post_stack_does_not_stretch_or_colour_correct() -> None:
    """The composite it saves is still linear and still carries its colour cast."""
    comp = _linear_sky(200, 260)
    out, _ = apply_post_stack(comp, np.full((200, 260), 50, dtype=np.int32))
    assert np.allclose(out, np.nan_to_num(comp), atol=1e-6)


# -- 2. background extraction (editor pre-stage) --------------------------


def test_background_gradient_is_flattened() -> None:
    comp = _linear_sky(300, 400)
    flattened, gradient = extract_background(comp)

    strip = flattened[100:150, 60:340].mean(axis=2)
    raw = comp[100:150, 60:340].mean(axis=2)
    assert float(np.std(strip) / np.mean(strip)) < 0.15
    assert float(np.std(strip) / np.mean(strip)) < float(np.std(raw) / np.mean(raw)) / 2
    assert gradient > 0.005  # it removed roughly the injected gradient


def test_background_extraction_strength_scales_the_subtraction() -> None:
    comp = _linear_sky(240, 320)
    _, full = extract_background(comp, strength=1.0)
    _, half = extract_background(comp, strength=0.5)
    _, off = extract_background(comp, strength=0.0)
    assert off == 0.0
    assert half < full
    assert abs(half - full / 2) < full * 0.1


def test_low_order_fit_does_not_carve_a_bright_nebula() -> None:
    """A degree-2 background surface cannot dig a hole out of a compact object."""
    comp = _linear_sky(300, 300)
    ny, nx = np.mgrid[0:300, 0:300]
    blob = np.exp(-(((ny - 150) / 22) ** 2 + ((nx - 150) / 22) ** 2)).astype(np.float32)
    comp += blob[:, :, np.newaxis] * np.array([0.03, 0.012, 0.009], dtype=np.float32)

    out, _ = extract_background(comp)

    nebula = float(out[135:165, 135:165].mean())
    background = float(out[30:70, 30:70].mean())
    assert nebula > background * 2.5  # the object still stands well clear of the sky


def test_background_extraction_is_finite_and_non_negative() -> None:
    comp = _linear_sky(160, 200)
    comp[10, 10] = np.nan  # a stray blank pixel
    out, _ = extract_background(np.nan_to_num(comp))
    assert np.isfinite(out).all()
    assert float(out.min()) >= 0.0


# -- 3. colour calibration (editor pre-stage) ---------------------------


def test_background_is_neutralised_and_channels_balanced() -> None:
    comp = _linear_sky(200, 260)
    flattened, _ = extract_background(comp)
    out, gains = calibrate_colour(flattened)
    sky = out[40:90, 40:120].reshape(-1, 3).mean(axis=0)
    assert float(sky.max() - sky.min()) < 0.002  # background is grey, not red-cast
    assert all(np.isfinite(g) for g in gains)


# -- 4. the whole pre-stage (linear composite -> BGR ready for the editor) --


def test_render_stack_base_returns_bgr_float_in_range() -> None:
    comp = _linear_sky(200, 260)
    out = render_stack_base(comp, StackParameters())
    assert out.shape == (200, 260, 3)
    assert out.dtype == np.float32
    assert float(out.min()) >= 0.0
    assert float(out.max()) <= 1.0


def test_render_stack_base_stretch_control_lifts_the_background() -> None:
    comp = _linear_sky(200, 260)
    subtle = render_stack_base(comp, StackParameters(stretch=0.0))
    aggressive = render_stack_base(comp, StackParameters(stretch=1.0))
    assert float(aggressive.mean()) > float(subtle.mean())


def test_render_stack_base_handles_a_mono_composite() -> None:
    rng = np.random.default_rng(2)
    mono = rng.random((120, 160)).astype(np.float32) * 0.02 + 0.01
    out = render_stack_base(mono, StackParameters())
    assert out.shape == (120, 160, 3)
    assert np.isfinite(out).all()
