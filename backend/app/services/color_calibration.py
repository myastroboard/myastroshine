"""Colour calibration of a linear composite against its own star field.

Two steps, both linear and both run by :func:`app.services.post_stack.render_stack_base`
ahead of the stretch:

* :func:`neutralise_sky` subtracts each channel's own sky level **without
  clipping** - clipping the negative half of the sky noise at zero leaves a
  positive bias proportional to each channel's noise, which a later channel gain
  (a Seestar's weak blue is boosted ~4x) turns into a purple, mottled background.
* :func:`star_white_balance` measures the colour of the unsaturated stars by
  aperture photometry and returns the per-channel gains that make the median star
  white. A field star population averages out close to a neutral (solar-type)
  colour, so this is the white reference PixInsight's ColorCalibration and Siril's
  "stars as white reference" use - unlike balancing the channel *means*, it is not
  pulled toward grey by a strongly coloured target (a red emission nebula, the
  blue Pleiades reflection nebula) filling the frame.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.logging_config import get_logger

logger = get_logger(__name__)

LUMA_RGB = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)

# Photometry runs on a copy no larger than this: INTER_AREA downscaling keeps each
# star's flux ratios intact, and the star count stays in the hundreds either way.
_PHOTOMETRY_MAX_SIZE = 2048
_DETECT_SIGMA = 8.0  # a star's band-passed peak must clear the noise by this much
_MIN_STAR_AREA = 4  # px - below this a detection is noise or a hot pixel
_MAX_STAR_AREA = 400  # px - above this it is a galaxy core / nebula knot, not a star
_SATURATION_LEVEL = 0.9  # a star touching this in any channel is non-linear - skipped
_MAX_CANDIDATES = 1500  # brightest detections measured (bounds the per-star loop)
_MAX_REFERENCE_STARS = 400  # the best-SNR stars that set the white reference
_MIN_REFERENCE_STARS = 20  # fewer than this and the median is not trusted
_GAIN_CLIP = (0.25, 6.0)  # a real OSC sensor cast stays well inside this
_SKY_LUMA_PERCENTILE = 50.0  # the sky is sampled on the darker half of the frame
_TINY = 1e-8


def neutralise_sky(linear: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Subtract each channel's sky level, keeping the (signed) noise around zero.

    The sky level is the per-channel median of the darker half of the frame (by
    luminance) - the sky between the objects on a typical deep-sky field, and still
    a sky-dominated sample on a frame-filling nebula. Returns ``(neutral, sky)``.
    """
    sample = linear[::3, ::3]
    luma = sample @ LUMA_RGB
    dark = luma <= np.percentile(luma, _SKY_LUMA_PERCENTILE)
    sky = np.median(sample[dark], axis=0).astype(np.float32)
    return (linear - sky).astype(np.float32), sky


def star_white_balance(linear: np.ndarray) -> np.ndarray | None:
    """Per-channel RGB gains that make the median unsaturated star white.

    ``linear`` is a sky-neutralised ``(H, W, 3)`` RGB composite. Stars are found on
    a band-passed luminance (so nebulosity and gradients do not register), each is
    measured in an aperture scaled to its size against the median of a surrounding
    annulus (the local sky, so a star on a nebula is not tinted by it), and the
    median ``R/G`` and ``B/G`` over the best-SNR stars set the gains. The gains are
    normalised to keep luminance unchanged. Returns ``None`` when too few clean
    stars were measured for the median to be trusted (the caller falls back).
    """
    rgb = _downscale(np.clip(linear, 0.0, None))
    fluxes = _star_fluxes(rgb)
    if len(fluxes) < _MIN_REFERENCE_STARS:
        logger.info("star colour calibration skipped", stars=len(fluxes))
        return None

    brightest = fluxes[np.argsort(-(fluxes @ LUMA_RGB))[:_MAX_REFERENCE_STARS]]
    reference = np.median(brightest / brightest[:, 1:2], axis=0)
    gains = np.clip(1.0 / np.maximum(reference, _TINY), *_GAIN_CLIP)
    normalised: np.ndarray = (gains / float(gains @ LUMA_RGB)).astype(np.float32)
    logger.info("star colour calibration", stars=len(brightest), gains=normalised.round(3).tolist())
    return normalised


def _downscale(rgb: np.ndarray) -> np.ndarray:
    height, width = rgb.shape[:2]
    scale = _PHOTOMETRY_MAX_SIZE / max(height, width)
    if scale >= 1.0:
        return rgb.astype(np.float32, copy=False)
    size = (round(width * scale), round(height * scale))
    return cv2.resize(rgb.astype(np.float32), size, interpolation=cv2.INTER_AREA)


def _star_fluxes(rgb: np.ndarray) -> np.ndarray:
    """Background-subtracted aperture flux ``(N, 3)`` of each clean, unsaturated star."""
    luma = rgb @ LUMA_RGB
    band = cv2.GaussianBlur(luma, (0, 0), 1.0) - cv2.GaussianBlur(luma, (0, 0), 6.0)
    center = float(np.median(band))
    noise = float(np.median(np.abs(band - center))) * 1.4826 + _TINY
    mask = (band > center + _DETECT_SIGMA * noise).astype(np.uint8)
    count, _, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count <= 1:
        return np.empty((0, 3), dtype=np.float32)

    areas = stats[1:, cv2.CC_STAT_AREA]
    candidates = np.flatnonzero((areas >= _MIN_STAR_AREA) & (areas <= _MAX_STAR_AREA)) + 1
    candidates = candidates[np.argsort(-areas[candidates - 1])][:_MAX_CANDIDATES]

    peak = rgb.max(axis=2)
    height, width = luma.shape
    rows: list[np.ndarray] = []
    for label in candidates:
        cx, cy = centroids[label]
        radius = max(3, int(np.sqrt(stats[label, cv2.CC_STAT_AREA] / np.pi) * 2.0))
        x0, x1 = int(cx) - 2 * radius, int(cx) + 2 * radius + 1
        y0, y1 = int(cy) - 2 * radius, int(cy) + 2 * radius + 1
        if x0 < 0 or y0 < 0 or x1 > width or y1 > height:
            continue
        if peak[y0:y1, x0:x1].max() > _SATURATION_LEVEL:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1]
        dist = np.hypot(xx - cx, yy - cy)
        aperture = dist <= radius
        annulus = (dist > 1.4 * radius) & (dist <= 2 * radius)
        patch = rgb[y0:y1, x0:x1]
        flux = (patch[aperture] - np.median(patch[annulus], axis=0)).sum(axis=0)
        if (flux > 0).all():
            rows.append(flux)
    return np.array(rows, dtype=np.float32).reshape(-1, 3)
