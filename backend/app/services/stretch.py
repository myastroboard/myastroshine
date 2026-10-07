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

Negative family values lower the white point (a midtone transfer, for a faint
object that needs lifting), with a highlight shoulder above the lowered white's
knee so everything brighter than the object rolls off toward 1 instead of
clipping to a flat white plateau; positive values keep the white point and add an
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
_DARK_SKY_PERCENTILE = 0.5  # wide_field: the darkest real sky stays above black
_DARK_SKY_MARGIN = 0.15  # ... by this fraction of its distance to the sky level
_OBJECT_PERCENTILE = 99.0
#: wide_field: a pixel keeps the fraction ``s / (s + this many noise sigma)`` of
#: its colour, ``s`` its own level above the black point - see adaptive_stretch.
_COLOUR_NOISE_SIGMA = 8.0
_OBJECT_TARGET = 0.72
_WHITE_PERCENTILE = 99.99  # of the brightest channel - stars included
_FAMILY_RANGE = (-1.0, 1.0)  # lowered white point .. strongest arcsinh compression
_ARCSINH_DECADES = 3.0  # family value 1 -> arcsinh beta ~ 10^3
_SHOULDER_KNEE = 0.6  # of the lowered white point - above it highlights roll off, never clip
_SOLVE_ITERATIONS = 40
_CLIPPED_SOURCE_LEVEL = 0.9  # a source pixel this bright may be clipped - its colour is not trusted
_CLIPPED_RAMP = 0.08
_TINY = 1e-7
_MIN_ARCSINH_BETA = 1e-3  # below this the arcsinh stage is an identity - skip it


def adaptive_stretch(
    linear: np.ndarray,
    target_background: float,
    source_peak: np.ndarray | None = None,
    sky_mask: np.ndarray | None = None,
    *,
    wide_field: bool = False,
) -> np.ndarray:
    """Sky-neutral linear RGB ``(H, W, 3)`` -> stretched BGR ``float32`` ``[0, 1]``.

    ``linear`` should already have its per-channel sky removed (signed values are
    fine - the black point clips them). ``source_peak`` is the brightest channel of
    the *unprocessed* composite: where it approaches saturation the recorded colour
    is an artefact of one channel clipping first, so the stretched pixel is faded
    to neutral instead of showing a coloured ring in a bright star's core.
    ``sky_mask`` (boolean, same size) takes the sky level, noise and object level
    from a nightscape's sky only, so a dark landscape does not set the black point.

    ``wide_field`` (a Milky Way / night landscape lens - see ``RenderHints``)
    changes two things:

    - the black point stays under the darkest real sky (its
      ``_DARK_SKY_PERCENTILE``) even when the noise is low: a wide field's sky is
      never perfectly flat, and a deep stack's low noise otherwise lifted the
      black point (sky - 2.8 sigma) toward the sky level and crushed the darker
      regions to black blotches;
    - the colour fades toward grey where the signal is near the noise. The
      colour rides as a ratio to the luminance, and on the sky - 2.8 sigma above
      black - that ratio is mostly the colour noise, amplified by the stretch.
      A deep-sky stack's colour noise is fine-grained and the chroma denoise
      takes it; a phone's night shot carries it at every scale up to tens of
      pixels (its merge and denoise smear it into blotches), so real iPhone
      frames came out covered in green and magenta mottle. Each pixel keeps
      ``s / (s + _COLOUR_NOISE_SIGMA * noise)`` of its colour, ``s`` its level
      above the black point: about a quarter on the sky, two thirds on the
      Milky Way's bright parts, nearly all of it in a star. A stack, with less noise,
      keeps more.
    """
    rgb = linear.astype(np.float32, copy=False)
    luma = rgb @ LUMA_RGB
    sky, noise, smooth, in_sky = _sky_noise(luma, sky_mask)
    black = sky - _SHADOW_CLIP_SIGMA * noise
    if wide_field:
        darkest = float(np.percentile(smooth[in_sky], _DARK_SKY_PERCENTILE))
        black = min(black, darkest - (sky - darkest) * _DARK_SKY_MARGIN)

    white = float(np.percentile(rgb[::2, ::2].max(axis=2) - black, _WHITE_PERCENTILE))
    white = max(white, _TINY)
    x_sky = max(sky - black, _TINY) / white
    x_obj = float(np.percentile(smooth[in_sky] - black, _OBJECT_PERCENTILE)) / white
    x_obj = min(max(x_obj, x_sky * 1.5), 1.0)
    white_floor = min(max(x_obj * 1.2, x_sky * 4.0), 1.0)

    family = _solve_family(x_sky, x_obj, target_background, white_floor)
    x_luma = np.clip((luma - black) / white, _TINY, None)
    y_luma = _curve(x_luma, family, x_sky, target_background, white_floor)

    scaled = np.clip((rgb - black) / white, 0.0, None) * (y_luma / x_luma)[..., np.newaxis]
    if wide_field:
        grey = y_luma[..., np.newaxis]
        kept = x_luma / (x_luma + _COLOUR_NOISE_SIGMA * noise / white)
        scaled = grey + (scaled - grey) * kept[..., np.newaxis]
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


def _sky_noise(
    luma: np.ndarray, sky_mask: np.ndarray | None = None
) -> tuple[float, float, np.ndarray, np.ndarray]:
    """Sky level, noise sigma, the star-suppressed downscaled luminance, and the
    sky pixels of that downscaled copy (all of them without a ``sky_mask``)."""
    height, width = luma.shape
    scale = min(1.0, _ESTIMATE_MAX_SIZE / max(height, width))
    size = (max(round(width * scale), 8), max(round(height * scale), 8))
    small = cv2.resize(luma.astype(np.float32), size, interpolation=cv2.INTER_AREA)
    smooth = cv2.medianBlur(small, _STAR_SUPPRESS_KERNEL)
    in_sky = (
        np.ones(smooth.shape, dtype=bool)
        if sky_mask is None
        else cv2.resize(sky_mask.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST) > 0
    )
    sky = float(np.percentile(smooth[in_sky], _SKY_PERCENTILE))

    sample = np.ascontiguousarray(luma[::2, ::2], dtype=np.float32)
    residual = sample - cv2.medianBlur(sample, 3)
    sample_size = (sample.shape[1], sample.shape[0])
    darkest = cv2.resize(smooth, sample_size) <= np.percentile(
        smooth[in_sky], _NOISE_SAMPLE_PERCENTILE
    )
    if sky_mask is not None:
        darkest &= (
            cv2.resize(in_sky.astype(np.uint8), sample_size, interpolation=cv2.INTER_NEAREST) > 0
        )
    noise = float(np.median(np.abs(residual[darkest]))) * _MEDIAN_RESIDUAL_TO_SIGMA
    return sky, noise, smooth, in_sky


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
        u_max = 1.0 / white
        rate = _shoulder_rate(u_max)
        xs = _shoulder(x / white, u_max, rate)
        sky = float(_shoulder(np.array(x_sky / white), u_max, rate))
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


def _shoulder(u: np.ndarray, u_max: float, rate: float) -> np.ndarray:
    """Highlight shoulder: identity up to the knee, then log roll-off to ``u_max -> 1``.

    Lowering the white point lifts a faint object, but a hard clip at the lowered
    white would burn everything brighter than it - nebula filaments and stars -
    to a flat plateau. Above ``_SHOULDER_KNEE`` the range ``(knee, u_max]`` is
    instead compressed into ``(knee, 1]`` with a slope-continuous log curve (the
    role of GHS's highlight protection), so the brightest pixel lands exactly on 1.
    """
    if rate <= 0.0:
        return u
    knee = _SHOULDER_KNEE
    span = 1.0 - knee
    over = np.clip(u - knee, 0.0, None)
    rolled = knee + span * np.log1p(rate * over) / np.log1p(rate * (u_max - knee))
    result: np.ndarray = np.where(u > knee, rolled, u)
    return result


def _shoulder_rate(u_max: float) -> float:
    """The log rate giving the shoulder unit slope at the knee (0 = no shoulder).

    Solves ``span * a / log1p(a * (u_max - knee)) == 1`` by bisection in log
    space; the left side rises monotonically with ``a`` from ``span / (u_max -
    knee)`` (< 1 whenever ``u_max > 1``), so the root always exists.
    """
    depth = u_max - _SHOULDER_KNEE
    span = 1.0 - _SHOULDER_KNEE
    if u_max <= 1.0 + _TINY:
        return 0.0
    low, high = -9.0, 12.0  # log10 of the rate
    for _ in range(_SOLVE_ITERATIONS * 2):
        mid = 0.5 * (low + high)
        rate = 10.0**mid
        if span * rate / np.log1p(rate * depth) > 1.0:
            high = mid
        else:
            low = mid
    return float(10.0 ** (0.5 * (low + high)))


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
