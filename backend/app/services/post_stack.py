"""Post-stack cleanup of a linear composite (``initial_plan/12_STACKING_REBUILD.md``
Phase 4).

Runs on the ``float32`` composite straight out of :class:`IntegrationService`,
before it becomes an editable session:

1. **Crop the field-rotation wedge** - an alt-az mount rotates the field over the
   session, so the edges of the aligned stack are covered by only a handful of
   frames (noisy, discoloured). Crop to the region most frames actually reached.
2. **Background extraction** - fit a *low-order* polynomial to the sky between
   the objects and subtract it, flattening a light-pollution / sky-glow
   gradient. Low order by design: it physically cannot carve into a nebula.
3. **Colour calibration** - neutralise the sky (make the background grey) and
   balance the channels so the star field is roughly white.

Everything stays linear. A real stretch, denoise and photometric calibration
are still the editor's job; this only removes the artefacts that make a raw
stack look broken.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.logging_config import get_logger

logger = get_logger(__name__)

_COVERAGE_KEEP_FRACTION = 0.6  # keep a row/column if this fraction of it is well covered
_COVERAGE_WELL_COVERED = 0.5  # "well covered" = >= this fraction of the max frame count
_MAX_CROP_FRACTION = 0.45  # never crop away more than this much of either axis
_MIN_CROP_MARGIN = 4  # px - ignore a crop smaller than this (not worth the reframe)

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

_NEUTRAL_PERCENTILE = 20.0  # per-channel sky level for background neutralisation
_BALANCE_GAIN_CLIP = (0.5, 2.0)
_COLOR_NDIM = 3
_TINY = 1e-8


@dataclass(frozen=True)
class PostStackReport:
    cropped: tuple[int, int, int, int] | None  # (top, left, height, width) kept, or None
    background_gradient: float  # peak-to-peak of the subtracted background, in linear units
    channel_gains: tuple[float, float, float]  # R, G, B multipliers applied


def apply_post_stack(
    composite: np.ndarray, coverage: np.ndarray
) -> tuple[np.ndarray, PostStackReport]:
    """Crop, background-subtract and colour-calibrate a linear ``(H, W, 3)`` composite."""
    # _combine already emits 0 for an uncovered pixel; nan_to_num is just defensive.
    composite = np.nan_to_num(composite.astype(np.float32, copy=False))
    cropped, box = _crop_to_coverage(composite, coverage)
    flattened, gradient = _extract_background(cropped)
    calibrated, gains = _calibrate_colour(flattened)
    logger.info(
        "post-stack cleanup done",
        cropped=box is not None,
        background_gradient=round(gradient, 5),
        channel_gains=[round(g, 3) for g in gains],
    )
    return calibrated.astype(np.float32), PostStackReport(box, gradient, gains)


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

    if kept_height < (1 - _MAX_CROP_FRACTION) * height or kept_width < (
        1 - _MAX_CROP_FRACTION
    ) * width:
        return composite, None  # would remove too much - something is off, leave it
    if trimmed < _MIN_CROP_MARGIN:
        return composite, None  # nothing meaningful to trim

    return (
        np.ascontiguousarray(composite[top:bottom, left:right]),
        (top, left, kept_height, kept_width),
    )


# -- 2. background extraction ----------------------------------------------


def _extract_background(composite: np.ndarray) -> tuple[np.ndarray, float]:
    """Fit a low-order polynomial to the object-free sky and subtract it.

    Object tiles (a nebula, a galaxy, a bright cluster) are rejected iteratively
    by their residual to the current fit and refitted, so the surface tracks the
    sky *between* the objects. A degree-2 fit can only be a smooth bowl - it
    cannot carve structure out of a nebula even if a few object tiles slip
    through.
    """
    height, width = composite.shape[:2]
    grid = np.linspace(0.0, 1.0, _BG_GRID, dtype=np.float32)
    grid_x, grid_y = np.meshgrid(grid, grid)
    row_edges = np.linspace(0, height, _BG_GRID + 1, dtype=int)
    col_edges = np.linspace(0, width, _BG_GRID + 1, dtype=int)
    full_y, full_x = np.mgrid[0:height, 0:width].astype(np.float32)
    norm_x, norm_y = full_x / max(width - 1, 1), full_y / max(height - 1, 1)

    background = np.zeros_like(composite)
    peak = 0.0
    for channel in range(_COLOR_NDIM):
        plane = composite[..., channel]
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

        surface = _eval_poly2d(norm_x, norm_y, coeffs, _BG_POLY_DEGREE)
        background[..., channel] = surface
        peak = max(peak, float(surface.max() - surface.min()))

    # Flatten toward the *darkest* real sky (a low percentile of the fitted
    # surface), not its median - keeps the sky dark so faint signal stays above it.
    flattened = composite - background + float(np.percentile(background, _BG_FLOOR_PERCENTILE))
    return np.clip(flattened, 0.0, None), peak


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


def _calibrate_colour(composite: np.ndarray) -> tuple[np.ndarray, tuple[float, float, float]]:
    """Neutralise the sky background, then balance the channels toward grey."""
    channels = [composite[..., c] for c in range(_COLOR_NDIM)]
    sky = np.array([np.percentile(ch, _NEUTRAL_PERCENTILE) for ch in channels])
    neutral = composite - (sky - sky.min())

    positive = np.clip(neutral, 0.0, None)
    means = np.array([positive[..., c].mean() for c in range(_COLOR_NDIM)]) + _TINY
    gains = np.clip(float(means.mean()) / means, *_BALANCE_GAIN_CLIP)
    balanced = np.clip(neutral * gains, 0.0, None)
    return balanced.astype(np.float32), (float(gains[0]), float(gains[1]), float(gains[2]))
