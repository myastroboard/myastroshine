"""Linear deconvolution of a stacked composite - the "Stack" step's sharpening.

Richardson-Lucy against the image's own point-spread function, measured on its
stars: what the atmosphere and the optics blurred, put back, on the linear data
and **before any noise reduction** ("Noise reduction of any kind should never be
applied before deconvolution of any kind" - RC Astro's BlurXTerminator /
NoiseXTerminator guidance; see docs/ALGORITHMS.md "Editing workflow"). It is the
first stage a composite goes through, ahead of the DeepSNR engine and of the
background extraction, colour calibration and stretch of ``post_stack``.

Nothing is invented: every step only redistributes the flux the stack recorded
(Richardson-Lucy conserves it), and the result is held back where it would not
be trustworthy - the sky background (no signal, only noise to amplify) and the
dark rings round bright stars that Richardson-Lucy is known for.
"""

from __future__ import annotations

from typing import cast

import cv2
import numpy as np

from app.logging_config import get_logger
from app.services.integration import highpass_noise
from app.services.star_detection import StarDetectionService
from app.utils.image_utils import _auto_stretch_to_uint8

logger = get_logger(__name__)

_COLOR_NDIM = 3
_LUMA_RGB = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)  # Rec. 709, linear RGB

# -- PSF measurement -------------------------------------------------------------
_DETECT_SENSITIVITY = 50
_DETECT_MAX_SIZE = 30
_MIN_PSF_STARS = 8  # fewer measurable stars: no trustworthy PSF, no deconvolution
_MAX_PSF_STARS = 300  # brightest-first; plenty for a median
_CUTOUT_RADIUS = 7  # px round each star (a 15x15 box)
_SATURATION_FRACTION = 0.8  # a peak above this fraction of the frame peak may be clipped
_MIN_PEAK_SNR = 15.0  # a peak this many noise sigma above its local sky
_MIN_PSF_SIGMA = 0.6  # px: below this the stars are undersampled - nothing to undo
_MAX_PSF_SIGMA = 6.0  # px: beyond this it is not a star (a galaxy core, a blend)

# -- Richardson-Lucy -------------------------------------------------------------
# Measured on real Seestar stacks (M 31, NGC 7000): the PSF read off the stars
# at face value and 20 iterations rang - a dark gap and a bright ring round every
# star. A PSF a little tighter than measured only under-corrects (it can never
# ring), and 10 iterations tighten the stars visibly with no ring.
_MAX_ITERATIONS = 10  # at amount 100
_PSF_SCALE = 0.8  # deconvolve with this fraction of the measured PSF sigma
_SIGNAL_SIGMA = 3.0  # full strength from this many noise sigma above the sky ...
_SIGNAL_RAMP = 2.0  # ... fading in from SIGNAL_SIGMA - RAMP
_FOOTPRINT_SIGMAS = 3.0  # a star's footprint reaches this many PSF sigma out
_DERING_SIGMAS = 3.0  # nothing may sink further than this many noise sigma below the sky
_EPS = 1e-6


def estimate_psf_sigma(luma: np.ndarray) -> float | None:
    """The Gaussian sigma (px) of the stars' PSF in a linear luminance plane.

    Measured by second moments on cut-outs of isolated, unsaturated, well-exposed
    stars (local sky subtracted), the median over them. ``None`` when too few
    stars qualify or the PSF is out of the deconvolvable range.
    """
    height, width = luma.shape
    detector = StarDetectionService()
    stars = detector.detect(_auto_stretch_to_uint8(luma), _DETECT_SENSITIVITY, _DETECT_MAX_SIZE)
    noise = max(highpass_noise(luma), _EPS)
    peak_limit = _SATURATION_FRACTION * float(luma.max())
    r = _CUTOUT_RADIUS
    yy, xx = np.mgrid[-r : r + 1, -r : r + 1].astype(np.float32)
    border = np.ones((2 * r + 1, 2 * r + 1), dtype=bool)
    border[2:-2, 2:-2] = False

    sigmas: list[float] = []
    for star in sorted(stars, key=lambda s: s.radius, reverse=True)[:_MAX_PSF_STARS]:
        x, y = round(star.x), round(star.y)
        if not (r <= x < width - r and r <= y < height - r):
            continue
        cut = luma[y - r : y + r + 1, x - r : x + r + 1]
        sky = float(np.median(cut[border]))
        flux = np.clip(cut - sky, 0.0, None)
        top = float(flux.max())
        if top + sky >= peak_limit or top < _MIN_PEAK_SNR * noise:
            continue
        total = float(flux.sum())
        cx = float((flux * xx).sum()) / total
        cy = float((flux * yy).sum()) / total
        var = float((flux * ((xx - cx) ** 2 + (yy - cy) ** 2)).sum()) / total / 2.0
        if var > 0:
            sigmas.append(var**0.5)
    if len(sigmas) < _MIN_PSF_STARS:
        logger.info("deconvolution skipped: too few measurable stars", stars=len(sigmas))
        return None
    sigma = float(np.median(sigmas))
    if not _MIN_PSF_SIGMA <= sigma <= _MAX_PSF_SIGMA:
        logger.info("deconvolution skipped: PSF out of range", sigma=round(sigma, 2))
        return None
    return sigma


def richardson_lucy(plane: np.ndarray, sigma: float, iterations: int) -> np.ndarray:
    """Richardson-Lucy deconvolution of a non-negative plane by a Gaussian PSF.

    The Gaussian is symmetric, so its mirror (the RL correction kernel) is itself.
    """
    observed = plane.astype(np.float32)
    estimate = observed.copy()
    for _ in range(iterations):
        blurred = cv2.GaussianBlur(estimate, (0, 0), sigmaX=sigma)
        ratio = observed / np.maximum(blurred, _EPS)
        estimate *= cv2.GaussianBlur(ratio, (0, 0), sigmaX=sigma)
    return estimate


def _local_background(plane: np.ndarray, sigma: float) -> np.ndarray:
    """What lies under the stars: the plane with every star-sized feature opened
    away (a galaxy, a nebula, the sky glow stay), smoothed, and lifted by the
    opening's own bias on the noise (it takes local minima) so the background
    sits on the sky's median, not below it."""
    reach = 2 * round(_FOOTPRINT_SIGMAS * sigma) + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (reach, reach))
    opened = cv2.morphologyEx(plane, cv2.MORPH_OPEN, kernel)
    smooth = cv2.GaussianBlur(opened, (0, 0), sigmaX=reach / 2.0)
    return cast("np.ndarray", smooth + float(np.median(plane - smooth)))


def _deconvolve_plane(
    plane: np.ndarray, sigma: float, iterations: int, weight: np.ndarray
) -> np.ndarray:
    """One plane through Richardson-Lucy, applied by ``weight`` and floored a few
    noise sigma under its own local background (no dark rings; the background's
    noise stays free to move, so no flux is added on average)."""
    floor = float(plane.min())
    sharpened = richardson_lucy(plane - floor + _EPS, sigma, iterations) + floor - _EPS
    noise = max(highpass_noise(plane), _EPS)
    background = _local_background(plane, sigma)
    delta = np.maximum(sharpened - plane, (background - _DERING_SIGMAS * noise) - plane)
    return cast("np.ndarray", plane + weight * delta)


def deconvolve(linear: np.ndarray, amount: int) -> np.ndarray:
    """Sharpen a linear composite (mono 2D, or RGB planes) by ``amount`` (0-100).

    Each plane is deconvolved on its own with the one PSF measured on the
    luminance's stars, so each redistributes only its own flux: colours keep
    their ratios through the colour calibration that follows (on the raw data a
    channel can be several times fainter than another - any mixing between them
    turns into coloured rings once balanced). ``amount`` sets the iterations (up
    to ``_MAX_ITERATIONS``). The change is applied where there is signal - from 1
    to 3 noise sigma of luminance above the *local* background (a star on a
    galaxy's bulge sits on the bulge), over each star's whole footprint, since
    Richardson-Lucy moves the wings' flux into the core and a weight fading out
    in the wings would keep the core's gain and drop the wings' loss. 0, a frame
    with too few measurable stars, or a PSF out of range return ``linear``
    unchanged.
    """
    if amount <= 0:
        return linear
    data = np.nan_to_num(linear.astype(np.float32, copy=False))
    luma = data @ _LUMA_RGB if data.ndim == _COLOR_NDIM else data
    luma = np.ascontiguousarray(luma, dtype=np.float32)
    measured = estimate_psf_sigma(luma)
    if measured is None:
        return linear
    sigma = _PSF_SCALE * measured
    iterations = max(1, round(_MAX_ITERATIONS * amount / 100.0))

    noise = max(highpass_noise(luma), _EPS)
    above = cv2.GaussianBlur(luma - _local_background(luma, sigma), (0, 0), max(sigma, 1.0))
    weight = np.clip((above / noise - (_SIGNAL_SIGMA - _SIGNAL_RAMP)) / _SIGNAL_RAMP, 0.0, 1.0)
    reach = 2 * round(_FOOTPRINT_SIGMAS * sigma) + 1
    weight = cv2.dilate(weight, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (reach, reach)))
    # Feathered: a hard footprint edge shows as a disc round each bright star.
    weight = cv2.GaussianBlur(weight, (0, 0), sigmaX=max(sigma, 1.0))

    logger.info("deconvolved", psf_sigma=round(sigma, 2), iterations=iterations)
    if data.ndim != _COLOR_NDIM:
        return _deconvolve_plane(luma, sigma, iterations, weight)
    planes = [
        _deconvolve_plane(np.ascontiguousarray(data[..., c]), sigma, iterations, weight)
        for c in range(_COLOR_NDIM)
    ]
    out: np.ndarray = np.stack(planes, axis=-1).astype(np.float32)
    return out
