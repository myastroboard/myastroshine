"""AutoAstroService - one-click enhancement, measured on the picture it improves.

Analyses the picture the editor starts from (the stacked composite's "Stack"
render, or the uploaded photo) and proposes a ``ProcessingParameters`` set that
showcases it: a darker - never clipped - sky, a lifted object, a neutral
background, the noise and colour mottle smoothed, and colour and stars dosed for
the kind of picture it is. See docs/ALGORITHMS.md "Auto Astro".

What it deliberately leaves alone: the "Stack" step, framing and the "Style"
look (the route carries them over), gradient and vignette correction (a single
frame cannot tell a gradient from an asymmetric object - see the docs), and the
tone sliders (contrast / exposure / highlights / shadows). An earlier version
drove those: ``shadows = -0.35`` plus a negative exposure crushed real stacks'
skies to black (M31: 24% of the sky at 0-2 of 255, its outer halo gone) and an
equal subtraction from every channel turned a faint sky cast into a magenta
tint. A tone curve does the same job without clipping and shows in the curve
editor as an ordinary, editable curve.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np

from app.logging_config import get_logger
from app.models import CurvePoint, ProcessingParameters
from app.services.star_detection import StarDetectionService
from app.utils.math_utils import curve_points_to_lut
from app.utils.sky_mask import fit_sky_mask
from app.utils.starlet import starlet_transform

logger = get_logger(__name__)

Scene = Literal["deep_sky", "landscape", "bright_on_black"]

_COLOR_NDIM = 3
_LEVELS = 255.0
_WHITE = 255  # the top 8-bit level, a curve's last point
_LUMA_BGR = (0.114, 0.587, 0.299)  # Rec. 601, as OpenCV's YCrCb

# -- measurement --------------------------------------------------------------
_ESTIMATE_MAX_SIZE = 800  # regions are found on a copy this size, star-suppressed
_STAR_SUPPRESS_KERNEL = 5
_BACKGROUND_PERCENTILE = 40.0  # the darker 40% of the sky (stars suppressed) is background
_OBJECT_PERCENTILE = 99.0  # the brightest real structure, stars suppressed
_OBJECT_FRACTION = 0.3  # object = above background + this fraction of the way to it
_MAD_TO_SIGMA = 1.4826
_FINEST_LAYER_NOISE = 0.889  # starlet layer 1 sigma for unit white noise
#: The sky's level and colour are read off a local mean (a box this wide): the
#: median of the raw pixels is not what the eye sees nor what the denoise leaves.
#: A dark sky's noisiest channel clips at 0 most, so its median sits under its
#: mean - a sky neutral by the median came out blue once denoised.
_SKY_MEAN_WINDOW = 7

# -- scene --------------------------------------------------------------------
#: A Moon or planet shot: a bright disc on a black, noise-free background.
_BLACK_BACKGROUND = 6.0
_BLACK_BACKGROUND_NOISE = 1.0
#: A sky this bright is not a dark-site deep-sky field: a light-polluted wide
#: field or a phone's processed night shot - treated like a night landscape.
_BRIGHT_SKY = 60.0

# -- tone curve ---------------------------------------------------------------
_MIN_OBJECT_CONTRAST = 12.0  # object level above the sky, below which no curve is drawn
_SKY_DEEPEN = 0.6  # the sky lands at this fraction of its level ...
_SKY_MAX_DROP = 25.0  # ... but never more than this many levels lower
_OBJECT_LIFT = 0.5  # the object moves this fraction of the way up to ...
_OBJECT_LIFT_TARGET = 128.0  # ... the middle grey (never down)
#: Steepest the curve may climb from the sky to the object: a faint object
#: (a JPEG of IC 5070, 18 levels above its sky) asked for ~4x, which posterised
#: 8-bit data and multiplied the noise just above the sky as much.
_MAX_CURVE_GAIN = 3.0

# -- noise --------------------------------------------------------------------
# The denoise strengths are noise thresholds relative to the measured noise (see
# app.utils.starlet), so these map how *visible* the noise is - its sigma on the
# 0-255 display scale, times the tone curve's gain above the sky, since the
# denoise runs after the curve - to how hard to cut it. Calibrated on real Seestar stacks
# (sigma 3-6) and JPEG uploads (1.5-4): above 40 the luma denoise smeared the
# faint stars of a dense field into a haze; chroma takes a harder cut since
# colour carries little detail.
_DENOISE_PER_SIGMA = 10.0
_DENOISE_NOISE_FLOOR = 0.5
_MAX_AUTO_DENOISE = 40
_CHROMA_DENOISE_PER_SIGMA = 14.0
_MAX_AUTO_CHROMA_DENOISE = 60
#: A camera night landscape (an iPhone ProRAW) arrives denoised at the finest
#: scale, so its sigma reads low, but carries coarse colour blotches.
_LANDSCAPE_MIN_CHROMA_DENOISE = 50

# -- colour -------------------------------------------------------------------
_GREEN_EXCESS = 0.03  # object green above the mean of red and blue, as a fraction of its luma
_AUTO_GREEN_REMOVAL = 50
_VIBRANCE_BASE = 1.15  # deep sky: a colour-preserving stretch leaves the colour pale
_VIBRANCE_RANGE = 0.35  # extra boost for a pale object (a galaxy), none for a vivid one
_VIBRANCE_CHROMA_TARGET = 80.0  # object chroma (0-255) that needs no extra boost

# -- stars --------------------------------------------------------------------
# Real star fields span orders of magnitude in density (tens per megapixel in a
# short frame, 4000+ in a Seestar stack of the Milky Way), hence a log scale.
_STAR_DENSITY_LOG_SCALE = 5.0
_STAR_DENSITY_OFFSET = 10.0  # below ~7 stars/MP nothing is reduced
_MAX_AUTO_STAR_REDUCTION = 30

_BRIGHT_OBJECT_SHARPNESS = 1.3  # noise-aware sharpening for a Moon / planet


@dataclass(frozen=True)
class Measurements:
    """What Auto Astro reads off a picture - luminance and colour on the 0-255 scale."""

    sky: float  # background luminance
    sky_bgr: tuple[float, float, float]  # background level of each channel
    #: Histograms (256 bins) of the background's B, G and R levels: what a tone
    #: curve does to the sky depends on the whole spread of its noise.
    sky_histograms: tuple[np.ndarray, np.ndarray, np.ndarray]
    object_level: float  # median luminance of the object
    object_chroma: float  # object's mean max-min channel spread
    green_excess: float  # object's mean G - (R+B)/2, as a fraction of its luminance
    luma_noise: float  # background noise sigma
    chroma_noise: float  # the noisier of the background's two chroma planes
    star_density: float  # detected stars per megapixel


class AutoAstroService:
    """Proposes enhancement parameters from a picture's own measurements."""

    def __init__(self, star_detector: StarDetectionService) -> None:
        self.star_detector = star_detector

    def suggest_parameters(
        self,
        image: np.ndarray,
        sky_mask: np.ndarray | None = None,
        *,
        wide_field: bool = False,
    ) -> ProcessingParameters:
        """Analyse ``image`` (BGR ``uint8``, the picture before any edit) and propose
        a parameter set.

        ``sky_mask`` (any resolution, high = sky) marks a night landscape's sky:
        the measurements skip the landscape. ``wide_field`` is a Milky Way lens
        (see ``RenderHints``). Either makes the scene a night landscape.
        """
        sky = None if image.ndim != _COLOR_NDIM else fit_sky_mask(sky_mask, image.shape)
        measured = self.measure(image, sky)
        camera_landscape = sky is not None or wide_field
        scene = _scene(measured, landscape=camera_landscape)
        parameters = _parameters(measured, scene, camera_landscape=camera_landscape)
        logger.info(
            "auto astro analysed",
            scene=scene,
            sky=round(measured.sky, 1),
            object_level=round(measured.object_level, 1),
            luma_noise=round(measured.luma_noise, 2),
            chroma_noise=round(measured.chroma_noise, 2),
            star_density=round(measured.star_density),
        )
        return parameters

    def measure(self, image: np.ndarray, sky: np.ndarray | None = None) -> Measurements:
        """Read the sky, the object, the noise and the stars off ``image``.

        ``sky`` (boolean, same size) limits every sky statistic to the sky of a
        night landscape.
        """
        bgr = image if image.ndim == _COLOR_NDIM else cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        pixels = bgr.astype(np.float32) / _LEVELS
        ycrcb = cv2.cvtColor(pixels, cv2.COLOR_BGR2YCrCb)
        luma = np.ascontiguousarray(ycrcb[..., 0])
        background, obj = _regions(luma, sky)

        window = (_SKY_MEAN_WINDOW, _SKY_MEAN_WINDOW)
        local_mean = cv2.blur(pixels, window)
        sky_bgr = tuple(
            float(np.median(local_mean[..., c][background])) * _LEVELS for c in range(3)
        )
        sky_level = float(np.median(cv2.blur(luma, window)[background])) * _LEVELS
        histograms = [np.bincount(bgr[..., c][background], minlength=_WHITE + 1) for c in range(3)]
        if obj.any():
            object_pixels = pixels[obj]
            object_luma = luma[obj]
            object_level = float(np.median(object_luma)) * _LEVELS
            spread = object_pixels.max(axis=1) - object_pixels.min(axis=1)
            green = object_pixels[:, 1] - 0.5 * (object_pixels[:, 0] + object_pixels[:, 2])
            object_chroma = float(spread.mean()) * _LEVELS
            green_excess = float(green.mean()) / max(float(object_luma.mean()), 1e-3)
        else:
            object_level, object_chroma, green_excess = float(np.median(luma)) * _LEVELS, 0.0, 0.0

        stars = self.star_detector.detect(bgr, sensitivity=50, max_size=30)
        megapixels = max(luma.size / 1_000_000.0, 0.01)
        return Measurements(
            sky=sky_level,
            sky_bgr=(sky_bgr[0], sky_bgr[1], sky_bgr[2]),
            sky_histograms=(histograms[0], histograms[1], histograms[2]),
            object_level=object_level,
            object_chroma=object_chroma,
            green_excess=green_excess,
            luma_noise=_background_noise(luma, background),
            chroma_noise=max(
                _background_noise(np.ascontiguousarray(ycrcb[..., 1]), background),
                _background_noise(np.ascontiguousarray(ycrcb[..., 2]), background),
            ),
            star_density=len(stars) / megapixels,
        )


def _regions(luma: np.ndarray, sky: np.ndarray | None) -> tuple[np.ndarray, np.ndarray]:
    """``(background, object)`` boolean masks at full resolution.

    Found on a downscaled, median-filtered (star-suppressed) copy: the background
    is the darker part of the sky, the object what rises well above it - the
    nebula or galaxy, not the stars. Never empty: a flat frame is all background.
    """
    height, width = luma.shape
    scale = min(1.0, _ESTIMATE_MAX_SIZE / max(height, width))
    size = (max(round(width * scale), 8), max(round(height * scale), 8))
    smooth = cv2.medianBlur(cv2.resize(luma, size, interpolation=cv2.INTER_AREA), 5)
    in_sky = (
        np.ones(smooth.shape, dtype=bool)
        if sky is None
        else cv2.resize(sky.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST) > 0
    )
    if not in_sky.any():
        in_sky[:] = True
    threshold = float(np.percentile(smooth[in_sky], _BACKGROUND_PERCENTILE))
    peak = float(np.percentile(smooth[in_sky], _OBJECT_PERCENTILE))
    background = in_sky & (smooth <= threshold)
    obj = in_sky & (smooth > threshold + _OBJECT_FRACTION * (peak - threshold))
    if peak <= threshold:
        obj[:] = False

    def full(mask: np.ndarray) -> np.ndarray:
        return (
            cv2.resize(mask.astype(np.uint8), (width, height), interpolation=cv2.INTER_NEAREST) > 0
        )

    return full(background), full(obj)


def _background_noise(plane: np.ndarray, background: np.ndarray) -> float:
    """White-noise sigma of ``plane`` over the background, on the 0-255 scale -
    read off the finest starlet layer (robust: a median absolute deviation)."""
    details, _ = starlet_transform(plane, 1)
    spread = float(np.median(np.abs(details[0][background]))) * _MAD_TO_SIGMA
    return spread / _FINEST_LAYER_NOISE * _LEVELS


def _scene(measured: Measurements, *, landscape: bool) -> Scene:
    if measured.sky < _BLACK_BACKGROUND and measured.luma_noise < _BLACK_BACKGROUND_NOISE:
        return "bright_on_black"
    if landscape or measured.sky > _BRIGHT_SKY:
        return "landscape"
    return "deep_sky"


def _parameters(
    measured: Measurements, scene: Scene, *, camera_landscape: bool
) -> ProcessingParameters:
    curves, gain = ({}, 1.0) if scene == "bright_on_black" else _tone_curves(measured)

    chroma_noise = measured.chroma_noise * gain
    chroma_denoise = int(
        np.clip(round(_CHROMA_DENOISE_PER_SIGMA * chroma_noise), 0, _MAX_AUTO_CHROMA_DENOISE)
    )
    if camera_landscape:
        chroma_denoise = max(chroma_denoise, _LANDSCAPE_MIN_CHROMA_DENOISE)
    denoise = round(_DENOISE_PER_SIGMA * (measured.luma_noise * gain - _DENOISE_NOISE_FLOOR))

    vibrance = 1.0
    star_reduction = 0
    if scene == "deep_sky":
        paleness = (_VIBRANCE_CHROMA_TARGET - measured.object_chroma) / _VIBRANCE_CHROMA_TARGET
        vibrance = round(_VIBRANCE_BASE + _VIBRANCE_RANGE * float(np.clip(paleness, 0.0, 1.0)), 2)
        density = _STAR_DENSITY_LOG_SCALE * math.log1p(measured.star_density)
        star_reduction = int(
            np.clip(round(density - _STAR_DENSITY_OFFSET), 0, _MAX_AUTO_STAR_REDUCTION)
        )

    return ProcessingParameters(
        **curves,
        denoise=int(np.clip(denoise, 0, _MAX_AUTO_DENOISE)),
        chroma_denoise=chroma_denoise,
        green_removal=(
            _AUTO_GREEN_REMOVAL
            if scene != "bright_on_black" and measured.green_excess > _GREEN_EXCESS
            else 0
        ),
        vibrance=vibrance,
        star_reduction=star_reduction,
        sharpness=_BRIGHT_OBJECT_SHARPNESS if scene == "bright_on_black" else 1.0,
    )


def _tone_curves(measured: Measurements) -> tuple[dict[str, list[CurvePoint]], float]:
    """The master tone curve, plus a per-channel curve for each channel whose sky
    is off neutral - and the curve's gain from the sky to the object (1 for no curve).

    The master curve keeps black at black (nothing clips), takes the sky down to
    ``_SKY_DEEPEN`` of its level and lifts the object toward the middle grey - the
    separation that makes an object stand out, drawn as a smooth monotone curve.
    A sky cast is additive (skyglow), so it is undone the way it was made: each
    off-neutral channel gets a curve that moves its sky - as the master curve left
    it - onto the neutral level, converging back to identity in the highlights.

    "As the master curve left it" is the mean of the curve over the sky's actual
    levels, not the curve at the sky's level: the noise straddles the bend where
    the curve steepens above the sky, which lifts the mean - a channel whose sky
    sits lower, on the straight part, is lifted less, and a sky neutral by the
    curve at its level came out cast once the denoise averaged it.
    """
    sky_x = round(measured.sky)
    object_x = round(measured.object_level)
    if (
        sky_x < 1
        or object_x >= _WHITE
        or measured.object_level < measured.sky + _MIN_OBJECT_CONTRAST
    ):
        return {}, 1.0
    sky_y = max(1, round(max(measured.sky * _SKY_DEEPEN, measured.sky - _SKY_MAX_DROP)))
    lifted = measured.object_level + _OBJECT_LIFT * max(
        0.0, _OBJECT_LIFT_TARGET - measured.object_level
    )
    steepest = sky_y + _MAX_CURVE_GAIN * (object_x - sky_x)
    object_y = min(round(lifted), _WHITE - 1, round(steepest))
    master = [(0, 0), (sky_x, sky_y), (object_x, object_y), (_WHITE, _WHITE)]
    curves: dict[str, list[CurvePoint]] = {"curve_points": _points(master)}

    lut = curve_points_to_lut(master)
    levels = [_mean_level(histogram, lut) for histogram in measured.sky_histograms]
    neutral = float(np.dot(levels, _LUMA_BGR))  # the grey of the same brightness
    target = round(neutral)
    for name, histogram, level in zip(
        ("blue", "green", "red"), measured.sky_histograms, levels, strict=True
    ):
        if abs(level - neutral) < 1.0 or not 0 < target < _WHITE:
            continue
        source = _channel_source(histogram, lut, target)
        if source != target:
            curves[f"{name}_curve_points"] = _points([(0, 0), (source, target), (_WHITE, _WHITE)])
    return curves, (object_y - sky_y) / (object_x - sky_x)


def _mean_level(histogram: np.ndarray, *luts: np.ndarray) -> float:
    """Mean level of a channel's sky after the ``luts`` (applied in order)."""
    levels = np.arange(histogram.size)
    for lut in luts:
        levels = lut[levels]
    return float((histogram * levels).sum() / max(int(histogram.sum()), 1))


def _channel_source(histogram: np.ndarray, master: np.ndarray, target: int) -> int:
    """The input level of a channel curve ``(0,0) - (source, target) - (255,255)``
    that brings the channel's sky, after ``master``, to ``target`` on average.

    Solved on the sky's histogram rather than set to its mean: lifting a starved
    channel takes a strongly concave curve, and over the spread of a noisy sky
    the mean of a concave curve falls short of the curve of the mean - a JPEG of
    IC 5070 kept a 4-level red cast. The mean falls as ``source`` rises, so a
    bisection finds it.
    """
    low, high = 1, _WHITE - 1
    while low < high:
        source = (low + high) // 2
        channel = curve_points_to_lut([(0, 0), (source, target), (_WHITE, _WHITE)])
        if _mean_level(histogram, master, channel) > target:
            low = source + 1
        else:
            high = source
    return low


def _points(pairs: list[tuple[int, int]]) -> list[CurvePoint]:
    return [CurvePoint(x=x, y=y) for x, y in pairs]
