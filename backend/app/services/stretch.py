"""Adaptive, colour-preserving stretch of a linear composite (the editor's default).

The classic auto-stretch (:func:`app.utils.image_utils.stretch_composite_linear`)
clips everything above the 99.9th percentile and applies one midtone transfer
function to each channel. On a real stack that burns a galaxy core to a flat white
disc (M31's core sits well below saturation in the linear data - the stretch is
what clips it) and pushes every star to a white, colourless plateau.

This stretch works on **luminance** and carries the colour along as a ratio
(``rgb * L' / L``, the approach of Lupton et al. 2004 and Siril's colour-preserving
asinh), so hue and saturation survive the stretch, and a pixel whose brightest
channel would exceed 1 is scaled down as a whole instead of clipped to white.

The luminance curve is picked per image from a one-parameter family, solved so
that two measured levels land where they should:

* the **sky** (a low percentile of a star-suppressed copy - not the frame median,
  which on a frame-filling nebula *is* the nebula) maps to ``target_background``;
* the **object** (a high percentile of that same star-suppressed copy - the
  bright nebula / galaxy body, not the star cores) maps to ``_OBJECT_TARGET``.

Negative family values lower the white point (a pure midtone transfer, for a
faint object that needs lifting); positive values keep the white point and add an
arcsinh stage underneath the midtone transfer, compressing the highlights so a
bright core keeps its structure. The black point is the sky minus a noise-scaled
margin, as in every STF-style auto-stretch.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.services.color_calibration import LUMA_RGB

_ESTIMATE_MAX_SIZE = 800  # star-suppressed copy the sky / object levels are read from
_STAR_SUPPRESS_KERNEL = 5  # median window on that copy - wipes stars, keeps nebulosity
_SKY_PERCENTILE = 10.0
_NOISE_SAMPLE_PERCENTILE = 30.0  # the noise is measured where the sky is darkest
# A 3x3-median residual underestimates the noise sigma; this puts it back on scale.
_MEDIAN_RESIDUAL_TO_SIGMA = 1.4826 * 1.5
_SHADOW_CLIP_SIGMA = 2.8  # black point = sky - this many noise sigma
_OBJECT_PERCENTILE = 99.0
_OBJECT_TARGET = 0.72
_WHITE_PERCENTILE = 99.99  # of the brightest channel - stars included
_FAMILY_RANGE = (-1.0, 1.0)  # lowered white point .. strongest arcsinh compression
_ARCSINH_DECADES = 3.0  # family value 1 -> arcsinh beta ~ 10^3
_SOLVE_ITERATIONS = 40
_CLIPPED_SOURCE_LEVEL = 0.9  # a source pixel this bright may be clipped - its colour is not trusted
_CLIPPED_RAMP = 0.08
_TINY = 1e-7
_MIN_ARCSINH_BETA = 1e-3  # below this the arcsinh stage is an identity - skip it


def adaptive_stretch(
    linear: np.ndarray,
    target_background: float,
    source_peak: np.ndarray | None = None,
) -> np.ndarray:
    """Sky-neutral linear RGB ``(H, W, 3)`` -> stretched BGR ``float32`` ``[0, 1]``.

    ``linear`` should already have its per-channel sky removed (signed values are
    fine - the black point clips them). ``source_peak`` is the brightest channel of
    the *unprocessed* composite: where it approaches saturation the recorded colour
    is an artefact of one channel clipping first, so the stretched pixel is faded
    to neutral instead of showing a coloured ring in a bright star's core.
    """
    rgb = linear.astype(np.float32, copy=False)
    luma = rgb @ LUMA_RGB
    sky, noise, smooth = _sky_noise(luma)
    black = sky - _SHADOW_CLIP_SIGMA * noise

    white = float(np.percentile(rgb[::2, ::2].max(axis=2) - black, _WHITE_PERCENTILE))
    white = max(white, _TINY)
    x_sky = max(sky - black, _TINY) / white
    x_obj = float(np.percentile(smooth - black, _OBJECT_PERCENTILE)) / white
    x_obj = min(max(x_obj, x_sky * 1.5), 1.0)
    white_floor = min(max(x_obj * 1.2, x_sky * 4.0), 1.0)

    family = _solve_family(x_sky, x_obj, target_background, white_floor)
    x_luma = np.clip((luma - black) / white, _TINY, None)
    y_luma = _curve(x_luma, family, x_sky, target_background, white_floor)

    scaled = np.clip((rgb - black) / white, 0.0, None) * (y_luma / x_luma)[..., np.newaxis]
    out = _fit_gamut(scaled, y_luma[..., np.newaxis])

    if source_peak is not None:
        near_clip = np.clip((source_peak - _CLIPPED_SOURCE_LEVEL) / _CLIPPED_RAMP, 0.0, 1.0)
        fade = cv2.GaussianBlur(near_clip.astype(np.float32), (0, 0), 1.5)[..., np.newaxis]
        out = out * (1.0 - fade) + out.max(axis=2, keepdims=True) * fade

    final = np.clip(out, 0.0, 1.0).astype(np.float32)
    bgr: np.ndarray = cv2.merge([final[..., 2], final[..., 1], final[..., 0]])  # RGB -> BGR
    return bgr


def _fit_gamut(rgb: np.ndarray, luma: np.ndarray) -> np.ndarray:
    """Bring a pixel whose brightest channel exceeds 1 back in range.

    Desaturates toward its own (stretched) luminance just enough to fit, so the
    brightness the curve chose is kept - scaling the whole pixel down instead
    visibly darkens a saturated colour (the blue halo round a Pleiades star turns
    into a dark ring). Hue is kept; only the saturation of the overflow gives.
    """
    peak = rgb.max(axis=2, keepdims=True)
    over = peak > 1.0
    headroom = np.clip(1.0 - luma, 0.0, None)
    keep = np.where(over, headroom / np.maximum(peak - luma, _TINY), 1.0)
    result: np.ndarray = luma + (rgb - luma) * keep
    return result


def _sky_noise(luma: np.ndarray) -> tuple[float, float, np.ndarray]:
    """Sky level, noise sigma, and the star-suppressed downscaled luminance."""
    height, width = luma.shape
    scale = min(1.0, _ESTIMATE_MAX_SIZE / max(height, width))
    small = cv2.resize(
        luma.astype(np.float32),
        (max(round(width * scale), 8), max(round(height * scale), 8)),
        interpolation=cv2.INTER_AREA,
    )
    smooth = cv2.medianBlur(small, _STAR_SUPPRESS_KERNEL)
    sky = float(np.percentile(smooth, _SKY_PERCENTILE))

    sample = np.ascontiguousarray(luma[::2, ::2], dtype=np.float32)
    residual = sample - cv2.medianBlur(sample, 3)
    darkest = cv2.resize(smooth, (sample.shape[1], sample.shape[0])) <= np.percentile(
        smooth, _NOISE_SAMPLE_PERCENTILE
    )
    noise = float(np.median(np.abs(residual[darkest]))) * _MEDIAN_RESIDUAL_TO_SIGMA
    return sky, noise, smooth


def _mtf(x: np.ndarray, balance: float) -> np.ndarray:
    """Midtones transfer function: ``(0,0)``, ``(balance, 0.5)``, ``(1,1)``."""
    result: np.ndarray = ((balance - 1.0) * x) / ((2.0 * balance - 1.0) * x - balance)
    return result


def _mtf_balance(x: float, target: float) -> float:
    """The MTF balance that maps ``x`` to ``target``."""
    return x * (target - 1.0) / (2.0 * x * target - x - target)


def _curve(
    x: np.ndarray, family: float, x_sky: float, target: float, white_floor: float
) -> np.ndarray:
    """One member of the stretch family, applied to normalised luminance ``x``."""
    if family < 0.0:
        white = white_floor ** (-family)  # 0 -> 1, -1 -> white_floor
        xs, sky = x / white, x_sky / white
    else:
        beta = 10.0 ** (_ARCSINH_DECADES * family) - 1.0
        if beta > _MIN_ARCSINH_BETA:
            norm = float(np.arcsinh(beta))
            xs = np.arcsinh(beta * x) / norm
            sky = float(np.arcsinh(beta * x_sky)) / norm
        else:
            xs, sky = x, x_sky
    sky = min(max(sky, _TINY), 1.0 - _TINY)
    return _mtf(np.clip(xs, 0.0, 1.0), _mtf_balance(sky, target))


def _solve_family(x_sky: float, x_obj: float, target: float, white_floor: float) -> float:
    """Bisect the family value that maps the object level to ``_OBJECT_TARGET``.

    The object's output falls monotonically as the family value rises; out-of-range
    solutions clamp to the nearest end.
    """
    low, high = _FAMILY_RANGE

    def object_out(family: float) -> float:
        return float(_curve(np.array(x_obj), family, x_sky, target, white_floor))

    if object_out(low) <= _OBJECT_TARGET:
        return low
    if object_out(high) >= _OBJECT_TARGET:
        return high
    for _ in range(_SOLVE_ITERATIONS):
        mid = 0.5 * (low + high)
        if object_out(mid) > _OBJECT_TARGET:
            low = mid
        else:
            high = mid
    return 0.5 * (low + high)
