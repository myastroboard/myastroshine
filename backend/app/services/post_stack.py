"""Post-stack cleanup of a linear composite (``initial_plan/12_STACKING_REBUILD.md``
Phase 4).

Two stages, split by *when* they run:

* :func:`apply_post_stack` runs once, in :class:`~app.services.stacking.StackingService`,
  the moment the composite comes out of :class:`~app.services.integration.IntegrationService`.
  It only **crops the field-rotation wedge** - an alt-az mount rotates the field
  over a session, so the edges of the aligned stack are covered by a handful of
  frames (noisy, discoloured). That crop defines the canvas, so it is baked into
  the saved ``composite.npy``.
* :func:`render_stack_base` runs on every editor render, turning that linear
  composite into the BGR image the enhancement pipeline works on:
  **background extraction** (fit a low-order polynomial to the sky between the
  objects and subtract it), **colour calibration** (neutralise the sky, balance
  the channels), then the **stretch** (screen-transfer-function auto-stretch with
  a tunable target background). All three are non-destructive - the editor's
  "Stack" step drives their strength and the linear composite is never touched.

Everything stays linear until the stretch. A real denoise and photometric
calibration are still the rest of the editor's job.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import cv2
import numpy as np

from app.logging_config import get_logger
from app.utils.image_utils import stretch_composite_linear

if TYPE_CHECKING:
    from app.models import StackParameters

logger = get_logger(__name__)

_COVERAGE_KEEP_FRACTION = 0.6  # keep a row/column if this fraction of it is well covered
_COVERAGE_WELL_COVERED = 0.5  # "well covered" = >= this fraction of the max frame count
_MAX_CROP_FRACTION = 0.45  # never crop away more than this much of either axis
_MIN_CROP_MARGIN = 4  # px - ignore a crop smaller than this (not worth the reframe)

# A single uploaded stack (a Seestar / alt-az live stack) has no per-pixel
# coverage array, so :func:`crop_low_signal_border` derives one from the pixels:
# the field-rotation / vignette footprint collapses one or more channels at the
# frame edge (the classic "red top / marked corners"), dropping them well below
# the interior sky level. A row/column is trimmed while too little of it stays
# above that floor - the same largest-centred-rectangle logic as the wedge crop.
_BORDER_ESTIMATE_MAX_SIZE = 384
_BORDER_INTERIOR = (0.35, 0.65)  # central box taken as the reference "good sky"
_BORDER_SKY_PERCENTILE = 40.0
_BORDER_SIGMA = 5.0  # a pixel is "dead" this many robust sigma below the interior sky
_BORDER_KEEP_FRACTION = 0.92  # keep a row/column while at least this much of it is live
_BORDER_MAX_CROP_FRACTION = 0.30  # a bigger trim than this means the detector is wrong - skip it

# The background is sampled on a GRID x GRID lattice; each tile's sky level is a
# low percentile of its pixels (the sky between the stars). A tile whose residual
# to the current fit is > OBJECT_SIGMA robust sigma holds an object and is
# dropped, then the surface is refitted (REJECT_ITERATIONS times). The fit is
# degree 2 - a paraboloid can only be a smooth gradient, never a nebula.
_BG_GRID = 22
_BG_TILE_PERCENTILE = 8.0
_BG_OBJECT_SIGMA = 1.8
_BG_REJECT_ITERATIONS = 3
_BG_POLY_DEGREE = 2
_BG_MIN_SAMPLES = 10  # below this many object-free tiles, fall back to a flat background
_BG_FLOOR_PERCENTILE = 10.0  # flatten the sky toward this percentile of the fitted surface
# Sample + fit the background on a copy no larger than this: the surface is a
# degree-2 polynomial (low-frequency by construction), so estimating it on a
# downscaled copy and cubic-resizing back loses nothing and keeps the whole
# thing fast enough to re-run on every editor render.
_BG_ESTIMATE_MAX_SIZE = 640

_NEUTRAL_PERCENTILE = 20.0  # per-channel sky level for background neutralisation
_BALANCE_GAIN_CLIP = (0.5, 2.0)
_COLOR_NDIM = 3
_TINY = 1e-8

# The editor "Stretch" control (0..1) maps onto the auto-stretch target
# background by log interpolation, so 0.5 lands on the composite default (0.10).
_STRETCH_TARGET_LOW = 0.05
_STRETCH_TARGET_HIGH = 0.20


@dataclass(frozen=True)
class PostStackReport:
    cropped: tuple[int, int, int, int] | None  # (top, left, height, width) kept, or None


def apply_post_stack(
    composite: np.ndarray, coverage: np.ndarray
) -> tuple[np.ndarray, PostStackReport]:
    """Crop the low-coverage rotation wedge off a linear ``(H, W, 3)`` composite."""
    # _combine already emits 0 for an uncovered pixel; nan_to_num is just defensive.
    composite = np.nan_to_num(composite.astype(np.float32, copy=False))
    cropped, box = _crop_to_coverage(composite, coverage)
    logger.info("post-stack wedge crop", cropped=box is not None, box=box)
    return cropped, PostStackReport(box)


def render_stack_base(composite: np.ndarray, params: StackParameters) -> np.ndarray:
    """Linear composite (already wedge-cropped) -> BGR ``float32`` ``[0, 1]``.

    Background extraction and colour calibration run first, in linear space and
    only when enabled; the stretch always runs, with a target background the
    "Stretch" control tunes. The output feeds straight into the enhancement
    pipeline's background/creative stages.
    """
    linear = np.nan_to_num(composite.astype(np.float32, copy=False))
    if linear.ndim == 2:  # noqa: PLR2004 - a mono stack: give the shared code 3 planes
        linear = np.repeat(linear[:, :, np.newaxis], _COLOR_NDIM, axis=2)

    if params.background_extraction > 0:
        linear, _ = extract_background(linear, params.background_extraction / 100.0)
    if params.color_calibration:
        linear, _ = calibrate_colour(linear)

    target = _STRETCH_TARGET_LOW * (_STRETCH_TARGET_HIGH / _STRETCH_TARGET_LOW) ** params.stretch
    return stretch_composite_linear(linear, target_background=target)


# -- 1. crop the rotation wedge ---------------------------------------------


def _crop_to_coverage(
    composite: np.ndarray, coverage: np.ndarray
) -> tuple[np.ndarray, tuple[int, int, int, int] | None]:
    height, width = coverage.shape
    peak = int(coverage.max())
    if peak <= 1:
        return composite, None
    well_covered = coverage >= _COVERAGE_WELL_COVERED * peak
    rows = well_covered.mean(axis=1) >= _COVERAGE_KEEP_FRACTION
    cols = well_covered.mean(axis=0) >= _COVERAGE_KEEP_FRACTION
    if not rows.any() or not cols.any():
        return composite, None

    top, bottom = int(np.argmax(rows)), height - int(np.argmax(rows[::-1]))
    left, right = int(np.argmax(cols)), width - int(np.argmax(cols[::-1]))
    kept_height, kept_width = bottom - top, right - left
    trimmed = (height - kept_height) + (width - kept_width)

    if (
        kept_height < (1 - _MAX_CROP_FRACTION) * height
        or kept_width < (1 - _MAX_CROP_FRACTION) * width
    ):
        return composite, None  # would remove too much - something is off, leave it
    if trimmed < _MIN_CROP_MARGIN:
        return composite, None  # nothing meaningful to trim

    return (
        np.ascontiguousarray(composite[top:bottom, left:right]),
        (top, left, kept_height, kept_width),
    )


def crop_low_signal_border(
    composite: np.ndarray,
) -> tuple[np.ndarray, tuple[int, int, int, int] | None]:
    """Trim a dead border off a single uploaded stack - no coverage map needed.

    A Seestar / alt-az live stack carries a field-rotation + vignette footprint
    at the frame edge: the outer rows/columns are built from far fewer sub-frames
    (and the telescope's own background subtraction over-corrects there), so one
    or more channels collapse well below the real sky level - the "red top /
    marked corners" a hard stretch then exaggerates. It is a sharp edge falloff,
    not a smooth gradient, so :func:`extract_background`'s degree-2 surface can
    neither model it nor fit cleanly around it; cropping it first is what lets
    the rest of the pre-stage work.

    The dead-pixel mask is derived from the pixels themselves (a pixel many
    robust sigma below the interior sky, in any channel), then the largest
    centred rectangle that stays mostly live is kept - the same logic as
    :func:`_crop_to_coverage`. Conservative by design: a legitimately dark or
    mildly vignetted edge is left alone, and an implausibly large trim is
    treated as a mis-detection and skipped. Returns ``(cropped, (top, left,
    height, width))`` or ``(composite, None)`` when nothing is trimmed.
    """
    linear = np.nan_to_num(composite.astype(np.float32, copy=False))
    planes = linear if linear.ndim == _COLOR_NDIM else linear[:, :, np.newaxis]
    height, width, channels = planes.shape

    scale = _BORDER_ESTIMATE_MAX_SIZE / max(height, width)
    small = (
        cv2.resize(
            planes,
            (max(round(width * scale), 16), max(round(height * scale), 16)),
            interpolation=cv2.INTER_AREA,
        )
        if scale < 1.0
        else planes
    )
    small = small if small.ndim == _COLOR_NDIM else small[:, :, np.newaxis]
    small_h, small_w = small.shape[:2]

    lo, hi = _BORDER_INTERIOR
    interior = small[
        round(small_h * lo) : round(small_h * hi), round(small_w * lo) : round(small_w * hi)
    ].reshape(-1, channels)
    sky = np.percentile(interior, _BORDER_SKY_PERCENTILE, axis=0)
    mad = np.median(np.abs(interior - np.median(interior, axis=0)), axis=0) * 1.4826
    floor = sky - _BORDER_SIGMA * mad - _TINY

    live = (small >= floor).all(axis=2)
    rows = live.mean(axis=1) >= _BORDER_KEEP_FRACTION
    cols = live.mean(axis=0) >= _BORDER_KEEP_FRACTION
    if not rows.any() or not cols.any():
        return composite, None

    inv = max(height, width) / max(small_h, small_w)
    top = round(int(np.argmax(rows)) * inv)
    bottom = height - round(int(np.argmax(rows[::-1])) * inv)
    left = round(int(np.argmax(cols)) * inv)
    right = width - round(int(np.argmax(cols[::-1])) * inv)
    top, left = max(top, 0), max(left, 0)
    bottom, right = min(bottom, height), min(right, width)
    kept_height, kept_width = bottom - top, right - left

    if (
        height - kept_height > _BORDER_MAX_CROP_FRACTION * height
        or width - kept_width > _BORDER_MAX_CROP_FRACTION * width
    ):
        return composite, None
    if (height - kept_height) + (width - kept_width) < _MIN_CROP_MARGIN:
        return composite, None

    return (
        np.ascontiguousarray(composite[top:bottom, left:right]),
        (top, left, kept_height, kept_width),
    )


# -- 2. background extraction ----------------------------------------------


def extract_background(composite: np.ndarray, strength: float = 1.0) -> tuple[np.ndarray, float]:
    """Fit a low-order polynomial to the object-free sky and subtract ``strength`` of it.

    Object tiles (a nebula, a galaxy, a bright cluster) are rejected iteratively
    by their residual to the current fit and refitted, so the surface tracks the
    sky *between* the objects. A degree-2 fit can only be a smooth bowl - it
    cannot carve structure out of a nebula even if a few object tiles slip
    through. The tile lattice is sampled on a downscaled copy and the fitted
    surface cubic-resized back to full resolution.
    """
    height, width = composite.shape[:2]
    scale = _BG_ESTIMATE_MAX_SIZE / max(height, width)
    small = (
        cv2.resize(
            composite,
            (max(round(width * scale), _BG_GRID), max(round(height * scale), _BG_GRID)),
            interpolation=cv2.INTER_AREA,
        )
        if scale < 1.0
        else composite
    )
    small_h, small_w = small.shape[:2]

    grid = np.linspace(0.0, 1.0, _BG_GRID, dtype=np.float32)
    grid_x, grid_y = np.meshgrid(grid, grid)
    row_edges = np.linspace(0, small_h, _BG_GRID + 1, dtype=int)
    col_edges = np.linspace(0, small_w, _BG_GRID + 1, dtype=int)

    background = np.zeros((height, width, _COLOR_NDIM), dtype=np.float32)
    peak = 0.0
    for channel in range(_COLOR_NDIM):
        plane = small[..., channel]
        samples = np.array(
            [
                [
                    float(
                        np.percentile(
                            plane[row_edges[i] : row_edges[i + 1], col_edges[j] : col_edges[j + 1]],
                            _BG_TILE_PERCENTILE,
                        )
                    )
                    for j in range(_BG_GRID)
                ]
                for i in range(_BG_GRID)
            ]
        )
        keep = np.ones_like(samples, dtype=bool)
        coeffs = _fit_poly2d(grid_x, grid_y, samples, _BG_POLY_DEGREE)
        for _ in range(_BG_REJECT_ITERATIONS):
            fitted = _eval_poly2d(grid_x, grid_y, coeffs, _BG_POLY_DEGREE).reshape(samples.shape)
            residual = samples - fitted
            sigma = np.median(np.abs(residual[keep] - np.median(residual[keep]))) * 1.4826 + _TINY
            keep = residual <= _BG_OBJECT_SIGMA * sigma
            if keep.sum() < _BG_MIN_SAMPLES:
                break
            keep = ~_dilate(~keep)  # also drop tiles touching an object (a soft skirt)
            coeffs = _fit_poly2d(grid_x[keep], grid_y[keep], samples[keep], _BG_POLY_DEGREE)

        surface_coarse = _eval_poly2d(grid_x, grid_y, coeffs, _BG_POLY_DEGREE)
        surface = cv2.resize(
            surface_coarse.astype(np.float32), (width, height), interpolation=cv2.INTER_CUBIC
        )
        background[..., channel] = surface
        peak = max(peak, float(surface.max() - surface.min()))

    # Flatten toward the *darkest* real sky (a low percentile of the fitted
    # surface), not its median - keeps the sky dark so faint signal stays above it.
    floor = float(np.percentile(background, _BG_FLOOR_PERCENTILE))
    flattened = composite - strength * (background - floor)
    return np.clip(flattened, 0.0, None), peak * strength


def _dilate(mask: np.ndarray) -> np.ndarray:
    """Grow a boolean lattice mask by one cell in each direction."""
    grown = mask.copy()
    grown[:-1] |= mask[1:]
    grown[1:] |= mask[:-1]
    grown[:, :-1] |= mask[:, 1:]
    grown[:, 1:] |= mask[:, :-1]
    return grown


def _poly_terms(x: np.ndarray, y: np.ndarray, degree: int) -> np.ndarray:
    """Design-matrix columns ``x^a y^b`` for all ``a + b <= degree``."""
    return np.stack(
        [x**a * y**b for total in range(degree + 1) for a in range(total + 1) for b in [total - a]],
        axis=-1,
    )


def _fit_poly2d(x: np.ndarray, y: np.ndarray, z: np.ndarray, degree: int) -> np.ndarray:
    terms = _poly_terms(x.ravel(), y.ravel(), degree)
    coeffs, *_ = np.linalg.lstsq(terms, z.ravel(), rcond=None)
    result: np.ndarray = coeffs
    return result


def _eval_poly2d(x: np.ndarray, y: np.ndarray, coeffs: np.ndarray, degree: int) -> np.ndarray:
    surface: np.ndarray = (_poly_terms(x, y, degree) @ coeffs).astype(np.float32)
    return surface


# -- 3. colour calibration -----------------------------------------------


def calibrate_colour(composite: np.ndarray) -> tuple[np.ndarray, tuple[float, float, float]]:
    """Neutralise the sky background, then balance the channels toward grey."""
    channels = [composite[..., c] for c in range(_COLOR_NDIM)]
    sky = np.array([np.percentile(ch, _NEUTRAL_PERCENTILE) for ch in channels])
    neutral = composite - (sky - sky.min())

    positive = np.clip(neutral, 0.0, None)
    means = np.array([positive[..., c].mean() for c in range(_COLOR_NDIM)]) + _TINY
    gains = np.clip(float(means.mean()) / means, *_BALANCE_GAIN_CLIP)
    balanced = np.clip(neutral * gains, 0.0, None)
    return balanced.astype(np.float32), (float(gains[0]), float(gains[1]), float(gains[2]))
