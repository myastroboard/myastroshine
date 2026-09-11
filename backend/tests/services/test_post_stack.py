"""Post-stack cleanup: crop the wedge (baked), then the non-destructive
background / colour / stretch pre-stage the editor drives."""

from __future__ import annotations

import numpy as np

from app.models import StackParameters
from app.services.post_stack import (
    _border_residual,
    apply_post_stack,
    calibrate_colour,
    crop_low_signal_border,
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


def test_crop_skips_when_at_most_one_frame_covers_any_pixel() -> None:
    """peak <= 1: there is no rotation wedge to speak of - single-frame coverage
    everywhere means nothing to trim."""
    comp = _linear_sky(50, 60)
    coverage = np.ones((50, 60), dtype=np.int32)
    out, report = apply_post_stack(comp, coverage)
    assert report.cropped is None
    assert out.shape[:2] == (50, 60)


def test_crop_skips_when_no_row_or_column_is_well_covered() -> None:
    """A scattered (non-rectangular) coverage pattern where every row and every
    column falls under the keep-fraction threshold - nothing qualifies to crop to."""
    height, width = 40, 40
    coverage = np.zeros((height, width), dtype=np.int32)
    coverage[:, ::2] = 10  # every other column covered; every row is only 50% covered
    comp = _linear_sky(height, width)
    out, report = apply_post_stack(comp, coverage)
    assert report.cropped is None
    assert out.shape[:2] == (height, width)


def test_crop_skips_when_the_well_covered_region_is_too_small() -> None:
    """rows/cols each qualify somewhere, but the resulting kept rectangle would
    remove more than _MAX_CROP_FRACTION of an axis - treated as a mis-detection."""
    height, width = 100, 100
    coverage = np.zeros((height, width), dtype=np.int32)
    coverage[:, :10] = 10  # a narrow strip, fully covered top-to-bottom
    coverage[:50, 10:] = 10  # the rest of the frame covered only in its top half
    comp = _linear_sky(height, width)
    out, report = apply_post_stack(comp, coverage)
    assert report.cropped is None
    assert out.shape[:2] == (height, width)


def test_apply_post_stack_does_not_stretch_or_colour_correct() -> None:
    """The composite it saves is still linear and still carries its colour cast."""
    comp = _linear_sky(200, 260)
    out, _ = apply_post_stack(comp, np.full((200, 260), 50, dtype=np.int32))
    assert np.allclose(out, np.nan_to_num(comp), atol=1e-6)


# -- 1b. border crop for a single uploaded stack (no coverage map) --------


def _seestar_sky(height: int, width: int, dead: bool) -> np.ndarray:
    """A faint linear stack over a ~0.16 pedestal, optionally with the two top
    corners collapsed - the Seestar field-rotation / vignette footprint, where
    one or more channels drop well below the interior sky. Scale mirrors the
    real thing (sky sigma ~1.5e-4, a several-hundred-ADU collapse at the edge)."""
    rng = np.random.default_rng(4)
    rgb = 0.16 + rng.normal(0, 0.00015, (height, width, 3)).astype(np.float32)
    if dead:
        rgb[: height // 6, : width // 8, :] -= 0.005  # top-left corner
        rgb[: height // 4, -width // 6 :, 1:] -= 0.006  # top-right corner (G/B)
    return rgb


def test_border_crop_trims_a_collapsed_edge() -> None:
    comp = _seestar_sky(600, 400, dead=True)
    cropped, box = crop_low_signal_border(comp)

    assert box is not None
    top, left, height, width = box
    assert top > 0  # the dead top band is gone
    assert left > 0 or width < 400  # and at least one collapsed corner's side
    assert cropped.shape[:2] == (height, width)
    assert np.isfinite(cropped).all()
    # the interior is untouched
    assert cropped.shape[0] > 600 * 0.6 and cropped.shape[1] > 400 * 0.6


def test_border_crop_leaves_a_clean_frame_alone() -> None:
    comp = _seestar_sky(600, 400, dead=False)
    cropped, box = crop_low_signal_border(comp)
    assert box is None
    assert cropped.shape[:2] == (600, 400)


def test_border_crop_handles_a_mono_composite() -> None:
    rng = np.random.default_rng(5)
    mono = 0.02 + rng.normal(0, 0.0002, (300, 400)).astype(np.float32)
    mono[:40, :80] -= 0.01  # a dead top-left corner
    cropped, box = crop_low_signal_border(mono)
    assert box is not None
    assert cropped.ndim == 2
    assert box[0] > 0


def test_border_crop_returns_none_when_almost_nothing_is_live() -> None:
    """The interior reference box reads as good sky, but almost the whole
    frame sits far below it - no row or column stays live enough to keep."""
    height, width = 120, 160
    comp = np.full((height, width, 3), -10.0, dtype=np.float32)
    lo, hi = 0.35, 0.65
    comp[round(height * lo) : round(height * hi), round(width * lo) : round(width * hi), :] = 0.16
    cropped, box = crop_low_signal_border(comp)
    assert box is None
    np.testing.assert_array_equal(cropped, comp)


def test_border_crop_skips_when_the_live_region_is_too_small() -> None:
    """Rows qualify only within a narrow band and columns only within a narrow
    stripe (a cross shape) - both axes would need to crop away more than
    _BORDER_MAX_CROP_FRACTION, so the detector treats it as unreliable."""
    height, width = 120, 160
    comp = np.full((height, width, 3), -10.0, dtype=np.float32)
    band_lo, band_hi = round(height * 0.40), round(height * 0.60)
    stripe_lo, stripe_hi = round(width * 0.45), round(width * 0.55)
    comp[band_lo:band_hi, :, :] = 0.16  # a horizontal band, full width
    comp[:, stripe_lo:stripe_hi, :] = 0.16  # a vertical stripe, full height
    cropped, box = crop_low_signal_border(comp)
    assert box is None
    np.testing.assert_array_equal(cropped, comp)


def test_border_residual_returns_zero_with_too_few_object_free_tiles() -> None:
    """Fewer than _BG_MIN_SAMPLES tiles survived rejection - too little signal
    to trust an edge-residual correction, so it is skipped outright."""
    samples = np.random.default_rng(0).random((22, 22)).astype(np.float32)
    surface = np.zeros((22, 22), dtype=np.float32)
    keep = np.zeros((22, 22), dtype=bool)
    keep[0, 0] = True  # a single object-free tile, well under _BG_MIN_SAMPLES

    result = _border_residual(samples, surface, keep)

    np.testing.assert_array_equal(result, np.zeros_like(samples, dtype=np.float32))


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


def test_border_residual_removes_an_edge_only_colour_cast() -> None:
    """A sharp edge/corner cast one channel deep - the kind a paraboloid can't
    bend to - is taken by the frame-edge residual correction."""
    comp = _linear_sky(360, 300)
    yy, xx = np.mgrid[0:360, 0:300]
    # blue suppressed in a band down the top ~15% and harder in the top corners
    edge = np.clip(1.0 - yy / (360 * 0.15), 0.0, 1.0).astype(np.float32)
    corner = edge * np.clip(np.abs(xx / 150 - 1.0), 0.0, 1.0).astype(np.float32)
    comp[..., 2] -= 0.0015 * edge + 0.003 * corner

    flattened, _ = extract_background(np.clip(comp, 0.0, None))

    def cast(region: np.ndarray) -> float:
        m = region.reshape(-1, 3).mean(axis=0)
        return float(m.max() - m.min())

    raw_corner = cast(np.clip(comp, 0.0, None)[:40, :50])
    fixed_corner = cast(flattened[:40, :50])
    assert fixed_corner < raw_corner * 0.5  # the corner is much closer to neutral


def test_border_residual_leaves_the_interior_alone() -> None:
    """The residual correction is masked to the frame edge - a big frame-filling
    object in the centre is not clipped by it."""
    comp = _linear_sky(320, 320)
    ny, nx = np.mgrid[0:320, 0:320]
    halo = np.exp(-(((ny - 160) / 90) ** 2 + ((nx - 160) / 90) ** 2)).astype(np.float32)
    comp += halo[:, :, np.newaxis] * np.array([0.02, 0.02, 0.02], dtype=np.float32)

    out, _ = extract_background(comp)

    core = float(out[150:170, 150:170].mean())
    mid = float(out[95:115, 95:115].mean())
    assert core > mid > 0  # the halo still falls off smoothly, not stepped by a mask edge


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


def test_colour_balance_survives_a_large_shared_pedestal() -> None:
    """A single already-stacked upload (Seestar/ASIAIR) can carry a large flat
    offset common to every channel - the multi-frame stacker's own composite
    never has one (bias/dark already subtracted per sub-frame). The balance
    gain must be measured on the signal above each channel's own sky level,
    not on the raw pedestal-inclusive composite - otherwise the shared offset
    swamps the per-channel mean and the "balance toward grey" gain silently
    collapses to ~1 regardless of how skewed the real signal is."""
    height, width = 120, 120
    pedestal = 20_000.0  # dwarfs the signal below, like a real 16-bit stack
    comp = np.full((height, width, 3), pedestal, dtype=np.float32)
    comp += np.random.default_rng(2).normal(0, 3.0, comp.shape).astype(np.float32)

    # An object patch with a strong colour skew above the (shared, neutral)
    # pedestal - red and green much stronger than blue, like an uncalibrated
    # OSC sensor's response to a broadband target.
    patch = (slice(40, 80), slice(40, 80))
    comp[patch] += np.array([400.0, 250.0, 40.0], dtype=np.float32)

    out, gains = calibrate_colour(comp)

    assert max(gains) - min(gains) > 0.5  # a real, non-trivial correction - not a ~1.0 no-op
    assert gains[2] > gains[0]  # blue (the weak channel) is boosted more than red

    before = comp[patch].reshape(-1, 3).mean(axis=0) - pedestal
    after = out[patch].reshape(-1, 3).mean(axis=0) - float(out[:20, :20].mean())
    before_spread = float(before.max() - before.min()) / float(before.mean())
    after_spread = float(after.max() - after.min()) / float(after.mean())
    assert after_spread < before_spread * 0.5  # the object's colour is now far more neutral


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


def test_render_stack_base_can_skip_background_extraction_and_colour_calibration() -> None:
    """Both pre-stages are individually optional - off (0 / False) skips the
    corresponding call, only the stretch always runs."""
    comp = _linear_sky(120, 160)
    out = render_stack_base(comp, StackParameters(background_extraction=0, color_calibration=False))
    assert out.shape == (120, 160, 3)
    assert np.isfinite(out).all()


def test_render_stack_base_handles_a_mono_composite() -> None:
    rng = np.random.default_rng(2)
    mono = rng.random((120, 160)).astype(np.float32) * 0.02 + 0.01
    out = render_stack_base(mono, StackParameters())
    assert out.shape == (120, 160, 3)
    assert np.isfinite(out).all()
