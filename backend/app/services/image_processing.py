"""ImageProcessingService - the single-image enhancement pipeline.

Algorithm details and the recommended operation order live in docs/ALGORITHMS.md.
Every stage takes and returns a **BGR float32** array in ``[0, 1]``;
:meth:`ImageProcessingService.apply_parameters` converts the ``uint8`` input to
float once on the way in and back once on the way out, so a value is quantised
only at the edges of the pipeline instead of after every stage - this matters
for a stacked composite pushed hard through the tone chain. Stages that are
genuinely uint8-native (LUT curves, HSV saturation, bilateral denoise, the star
detector) keep a short local round-trip. Each stage is an identity transform
when its parameter sits at the default.
"""

from __future__ import annotations

import functools
import math
from collections.abc import Callable
from typing import cast

import cv2
import numpy as np

from app.logging_config import get_logger
from app.models import CurvePoint, GeometryParameters, LookParameters, ProcessingParameters
from app.services.external_starless import StarlessSplitFn
from app.services.looks import LooksService
from app.services.post_stack import RenderHints, render_stack_base
from app.services.star_detection import StarDetectionService
from app.services.starless import StarlessService
from app.utils.math_utils import (
    curve_points_to_lut,
    kelvin_to_rgb_gain,
    tint_to_rgb_gain,
)
from app.utils.starlet import denoise_plane, enhance_detail

StepCallback = Callable[[str, int], None]
#: ``(image, linear) -> denoised``, ``float32`` in and out. ``linear`` is true when
#: the stage runs on a linear stacked composite (RGB planes, before the stretch).
DenoiseStageFn = Callable[[np.ndarray, bool], np.ndarray]

logger = get_logger(__name__)

_EPS = 1e-3  # a parameter within this of its default is treated as "unchanged"
_NEUTRAL_KELVIN = 6500
_LUMA_BGR = np.array([0.0722, 0.7152, 0.2126], dtype=np.float32)
_DENOISE_MAX_SIGMAS = 3.0  # luma denoise at 100: shrink coefficients up to 3 noise sigma
_DENOISE_LAYERS = 4
_CHROMA_DENOISE_MAX_SIGMAS = 4.0  # colour noise can take a harder cut than luma
_CHROMA_DENOISE_LAYERS = 5
_SHARPEN_GAIN = 1.5  # sharpness 2.0 -> fine-scale detail boosted by 1 + 1.5
_SHARPEN_LAYERS = 2
_STAR_FALLOFF_MARGIN = 1.6  # widen each star's blend footprint past its own radius
_DEHAZE_PATCH_SIZE = 15
_DEHAZE_ATMOSPHERE_FRACTION = 0.001  # brightest 0.1% of dark-channel pixels
_DEHAZE_MIN_ATMOSPHERIC_LIGHT = 0.2  # floor, so a very dark frame can't push this near zero
_DEHAZE_ESTIMATE_MAX_SIZE = 800  # dark-channel/transmission map; recovery itself runs at full res
_GRADIENT_ESTIMATE_MAX_SIZE = 256  # the background is smooth/low-frequency - a small copy is enough
_VIGNETTE_ESTIMATE_MAX_SIZE = 128  # the gain map depends only on position, not image content


def _unchanged(value: float, default: float) -> bool:
    return abs(value - default) < _EPS


def _to_u8(image: np.ndarray) -> np.ndarray:
    """BGR float32 ``[0, 1]`` -> BGR uint8, for a stage that is uint8-native."""
    packed: np.ndarray = np.clip(np.rint(image * 255.0), 0, 255).astype(np.uint8)
    return packed


def _to_f32(image: np.ndarray) -> np.ndarray:
    """BGR uint8 -> BGR float32 ``[0, 1]``."""
    return image.astype(np.float32) / 255.0


def _dtype_flexible[M: Callable[..., np.ndarray]](method: M) -> M:
    """Let a float32-``[0, 1]`` stage also accept (and return) a uint8 BGR frame.

    :meth:`ImageProcessingService.apply_parameters` drives the whole pipeline in
    float32 and never triggers the conversion. Direct callers - the upload
    geometry pass, the per-stage tests - can still hand in a plain uint8 image
    and get a uint8 image back, with a single round-trip at the boundary.
    """

    @functools.wraps(method)
    def wrapper(
        self: ImageProcessingService, image: np.ndarray, *args: object, **kwargs: object
    ) -> np.ndarray:
        if image.dtype == np.uint8:
            return _to_u8(method(self, _to_f32(image), *args, **kwargs))
        result: np.ndarray = method(self, image, *args, **kwargs)
        return result

    return cast("M", wrapper)


class ImageProcessingService:
    """Applies enhancement parameters to an image."""

    def __init__(self) -> None:
        self._star_detector = StarDetectionService()
        self._starless = StarlessService(self._star_detector)
        self._looks = LooksService()

    @_dtype_flexible
    def apply_geometry(self, image: np.ndarray, geom: GeometryParameters) -> np.ndarray:
        """Rotate / flip / straighten / crop the image before enhancement.

        Quarter turns are clockwise; ``straighten`` (deg) rotates about the
        centre and scales up so the frame stays full; the crop rectangle is in
        fractions of the rotated/flipped image.
        """
        if geom == GeometryParameters():
            return image

        result = image
        for _ in range(geom.rotate_quarters % 4):
            result = cv2.rotate(result, cv2.ROTATE_90_CLOCKWISE)
        if geom.flip_horizontal:
            result = cv2.flip(result, 1)
        if geom.flip_vertical:
            result = cv2.flip(result, 0)

        if abs(geom.straighten) > _EPS:
            height, width = result.shape[:2]
            rad = math.radians(abs(geom.straighten))
            cover = max(
                (width * math.cos(rad) + height * math.sin(rad)) / width,
                (width * math.sin(rad) + height * math.cos(rad)) / height,
            )
            matrix = cv2.getRotationMatrix2D((width / 2, height / 2), geom.straighten, cover)
            result = cv2.warpAffine(
                result,
                matrix,
                (width, height),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REFLECT,
            )

        if (geom.crop_x, geom.crop_y, geom.crop_w, geom.crop_h) != (0.0, 0.0, 1.0, 1.0):
            height, width = result.shape[:2]
            x0 = max(0, round(geom.crop_x * width))
            y0 = max(0, round(geom.crop_y * height))
            x1 = min(width, max(round((geom.crop_x + geom.crop_w) * width), x0 + 1))
            y1 = min(height, max(round((geom.crop_y + geom.crop_h) * height), y0 + 1))
            result = result[y0:y1, x0:x1].copy()

        return result

    @_dtype_flexible
    def apply_white_balance(self, image: np.ndarray, temperature: int, tint: int) -> np.ndarray:
        """Adjust colour temperature (2000-8000K, 6500 neutral) and tint (-50..50)."""
        if temperature == _NEUTRAL_KELVIN and tint == 0:
            return image
        r_gain, g_gain, b_gain = kelvin_to_rgb_gain(temperature)
        r_tint, g_tint, b_tint = tint_to_rgb_gain(tint)
        # image is BGR, so order the gains B, G, R.
        gains = np.array([b_gain * b_tint, g_gain * g_tint, r_gain * r_tint], dtype=np.float32)
        return np.clip(image * gains, 0.0, 1.0)

    @_dtype_flexible
    def apply_vignette_correction(self, image: np.ndarray, amount: int) -> np.ndarray:
        """Brighten (``+``) or darken (``-``) toward the corners (-100..100).

        A generic radial gain model, not a per-lens calibrated profile -
        nothing here knows what lens took the shot. The gain departs from 1 with
        squared distance from the image centre: ``+100`` lifts the corners by
        80% (counteracting lens vignetting), ``-100`` drops them to 20%
        (deepening a vignette for effect, or taming an over-corrected stack).
        The gain map depends only on position, not image content, so (like
        `apply_gradient_reduction`) it's computed on a small downscaled grid and
        resized up - full-resolution precision would be wasted work for a smooth
        analytic function.
        """
        if amount == 0:
            return image
        strength = amount / 100.0
        height, width = image.shape[:2]
        scale = _VIGNETTE_ESTIMATE_MAX_SIZE / max(height, width)
        small_h, small_w = (
            (round(height * scale), round(width * scale)) if scale < 1.0 else (height, width)
        )
        yy, xx = np.mgrid[0:small_h, 0:small_w].astype(np.float32)
        cy, cx = small_h / 2.0, small_w / 2.0
        max_dist = math.sqrt(cx**2 + cy**2)
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / max_dist
        gain_small = (1.0 + strength * (dist**2) * 0.8).astype(np.float32)
        gain = (
            cv2.resize(gain_small, (width, height), interpolation=cv2.INTER_LINEAR)
            if scale < 1.0
            else gain_small
        )
        return cast("np.ndarray", np.clip(image * gain[:, :, np.newaxis], 0.0, 1.0))

    @_dtype_flexible
    def apply_gradient_reduction(self, image: np.ndarray, amount: int) -> np.ndarray:
        """Flatten smooth background gradients - light pollution, sky glow (0-100).

        A very large Gaussian blur approximates the smooth background/gradient;
        genuine DSO structure is higher-frequency and survives mostly in the
        residual, so subtracting the blur's own deviation from its mean
        flattens the background without eating into real detail.

        The background is estimated on a small downscaled copy, then resized
        back up - a huge blur at full resolution (the naive approach) is
        computationally infeasible: an 8000px-wide frame would need a
        ~5000px-wide Gaussian kernel to reach the same effective sigma. A
        smooth low-frequency estimate doesn't lose anything by downscaling
        first (unlike star detection, which needs full resolution).
        """
        if amount <= 0:
            return image
        strength = amount / 100.0
        height, width = image.shape[:2]
        scale = _GRADIENT_ESTIMATE_MAX_SIZE / max(height, width)
        small = (
            cv2.resize(
                image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA
            )
            if scale < 1.0
            else image
        )
        sigma = max(small.shape[:2]) * 0.1
        background_small = cv2.GaussianBlur(small, (0, 0), sigmaX=sigma).astype(np.float32)
        correction_small = (background_small - background_small.mean()) * strength
        correction = cv2.resize(correction_small, (width, height), interpolation=cv2.INTER_LINEAR)
        return np.clip(image - correction, 0.0, 1.0)

    @_dtype_flexible
    def apply_dehaze(self, image: np.ndarray, amount: int) -> np.ndarray:
        """Dark-channel-prior haze removal (0-100).

        Restores contrast/colour saturation lost to a veiling glow (thin
        cloud, humidity, light-pollution haze) - distinct from
        `apply_gradient_reduction`'s smooth *background level* correction:
        this instead estimates a per-pixel "how much haze is in front of this"
        transmission map and divides it back out. Simplified from He et al.'s
        original (no guided-filter transmission refinement - the patch-erosion
        step already gives a reasonable, if blockier, map without a new
        dependency).

        The dark channel / atmospheric light / transmission map - the
        expensive steps (two large-kernel erosions over the whole frame) -
        are estimated on a downscaled copy; only the final per-pixel recovery
        formula (cheap) runs at full resolution, using the transmission map
        resized back up. Haze varies smoothly across a scene, so this loses
        little; at full 24MP the two erosions alone cost seconds.
        """
        if amount <= 0:
            return image
        strength = amount / 100.0
        img = image
        height, width = image.shape[:2]
        scale = _DEHAZE_ESTIMATE_MAX_SIZE / max(height, width)
        small = (
            cv2.resize(
                image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA
            )
            if scale < 1.0
            else img
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (_DEHAZE_PATCH_SIZE, _DEHAZE_PATCH_SIZE))

        dark_channel = cv2.erode(np.min(small, axis=2), kernel)
        flat_dark = dark_channel.reshape(-1)
        num_pixels = max(1, int(flat_dark.size * _DEHAZE_ATMOSPHERE_FRACTION))
        brightest_indices = np.argpartition(flat_dark, -num_pixels)[-num_pixels:]
        atmospheric_light = small.reshape(-1, 3)[brightest_indices].max(axis=0)
        atmospheric_light = np.clip(atmospheric_light, _DEHAZE_MIN_ATMOSPHERIC_LIGHT, 1.0)

        normalized_small = small / atmospheric_light
        transmission_small = 1.0 - strength * cv2.erode(np.min(normalized_small, axis=2), kernel)
        transmission_small = np.clip(transmission_small, 0.15, 1.0)
        transmission = (
            cv2.resize(transmission_small, (width, height), interpolation=cv2.INTER_LINEAR)
            if scale < 1.0
            else transmission_small
        )[:, :, np.newaxis]

        recovered = (img - atmospheric_light) / transmission + atmospheric_light
        return cast("np.ndarray", np.clip(recovered, 0.0, 1.0))

    @_dtype_flexible
    def apply_contrast(self, image: np.ndarray, contrast: float) -> np.ndarray:
        """Linear stretch about the image mean, with a gentle gamma (0.5..3.0)."""
        if _unchanged(contrast, 1.0):
            return image
        mean = float(image.mean())
        stretched = (image - mean) * contrast + mean
        gamma = 1.0 / max(1.0 + (contrast - 1.0) * 0.1, 0.5)
        return np.power(np.clip(stretched, 0.0, 1.0), gamma)

    @_dtype_flexible
    def apply_exposure(self, image: np.ndarray, exposure: float) -> np.ndarray:
        """Offset overall luminance (-1.0..1.0), scaled to +/- 50 levels of 255."""
        if _unchanged(exposure, 0.0):
            return image
        return np.clip(image + exposure * (50.0 / 255.0), 0.0, 1.0)

    @_dtype_flexible
    def apply_highlights_shadows(
        self, image: np.ndarray, highlights: float, shadows: float
    ) -> np.ndarray:
        """Recover bright / dark detail via luminance-masked tone curves (-1.0..1.0)."""
        if _unchanged(highlights, 0.0) and _unchanged(shadows, 0.0):
            return image
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        highlight_mask = np.square(gray)[:, :, np.newaxis]
        shadow_mask = np.square(1.0 - gray)[:, :, np.newaxis]
        img = image + highlight_mask * highlights * 0.3 + shadow_mask * shadows * 0.3
        return np.clip(img, 0.0, 1.0)

    @_dtype_flexible
    def apply_whites_blacks(self, image: np.ndarray, whites: float, blacks: float) -> np.ndarray:
        """Push the white / black clipping points (-1.0..1.0).

        Narrower and more aggressive than `apply_highlights_shadows` (``gray**4``
        vs ``gray**2`` weighting), so only the true near-white/near-black tail
        moves - the usual distinction between "Highlights"/"Shadows" (a broad
        upper/lower range) and "Whites"/"Blacks" (just the clipping point) in
        most photo editors.
        """
        if _unchanged(whites, 0.0) and _unchanged(blacks, 0.0):
            return image
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # np.square(np.square(x)) (x**4 via repeated squaring) is a fast path;
        # np.power(x, 4) is not - measurably so at 24MP.
        white_mask = np.square(np.square(gray))[:, :, np.newaxis]
        black_mask = np.square(np.square(1.0 - gray))[:, :, np.newaxis]
        img = image + white_mask * whites * 0.4 + black_mask * blacks * 0.4
        return np.clip(img, 0.0, 1.0)

    @_dtype_flexible
    def apply_tone_curve(self, image: np.ndarray, curve_points: list[CurvePoint]) -> np.ndarray:
        """Apply a user-drawn tone curve as a 256-entry LUT, identical on each channel.

        ``curve_points`` are ``(x, y)`` 8-bit input/output pairs spanning
        0-255; empty means no curve (identity). See
        :func:`app.utils.math_utils.curve_points_to_lut` for the interpolation.
        """
        if not curve_points:
            return image
        lut = curve_points_to_lut([(point.x, point.y) for point in curve_points])
        return _to_f32(cv2.LUT(_to_u8(image), lut))

    @_dtype_flexible
    def apply_channel_curves(
        self,
        image: np.ndarray,
        red_curve_points: list[CurvePoint],
        green_curve_points: list[CurvePoint],
        blue_curve_points: list[CurvePoint],
    ) -> np.ndarray:
        """Apply an independent tone curve to each of R/G/B (colour grading).

        Unlike :meth:`apply_tone_curve` (one curve applied identically to
        every channel), each channel gets its own curve here - for a colour
        cast at one specific tonal range that a single white-balance gain
        can't reach (e.g. a slightly green background sky only in the
        midtones), or deliberate creative grading (blue into the shadows,
        warm into the highlights). Runs after the master tone curve, so a
        curve is a fine-tuning layer on top of it, same relationship as the
        master curve has with the basic tone sliders. Any channel left empty
        (identity) is skipped independently of the others.
        """
        if not (red_curve_points or green_curve_points or blue_curve_points):
            return image
        blue, green, red = cv2.split(_to_u8(image))
        if blue_curve_points:
            blue = cv2.LUT(blue, curve_points_to_lut([(p.x, p.y) for p in blue_curve_points]))
        if green_curve_points:
            green = cv2.LUT(green, curve_points_to_lut([(p.x, p.y) for p in green_curve_points]))
        if red_curve_points:
            red = cv2.LUT(red, curve_points_to_lut([(p.x, p.y) for p in red_curve_points]))
        return _to_f32(cv2.merge([blue, green, red]))

    @_dtype_flexible
    def apply_saturation(self, image: np.ndarray, saturation: float) -> np.ndarray:
        """Scale each pixel's colour away from its own luminance (0.0..2.0).

        Luminance-preserving and in float: the brightness the tone stages chose is
        kept, and a faint, low-chroma nebula is not posterised the way an 8-bit
        HSV round-trip quantises it.
        """
        if _unchanged(saturation, 1.0):
            return image
        luma = (image @ _LUMA_BGR)[:, :, np.newaxis]
        return np.clip(luma + (image - luma) * saturation, 0.0, 1.0)

    @_dtype_flexible
    def apply_vibrance(self, image: np.ndarray, vibrance: float) -> np.ndarray:
        """Boost saturation weighted towards less-saturated pixels (0.0..2.0)."""
        if _unchanged(vibrance, 1.0):
            return image
        # Per-channel max/min: numpy's reduction over the interleaved last axis
        # costs several times more on a full-res frame.
        blue, green, red = cv2.split(image)
        peak = np.maximum(np.maximum(blue, green), red)
        sat = (peak - np.minimum(np.minimum(blue, green), red)) / np.maximum(peak, 1e-6)
        factor = (1.0 + (1.0 - sat) * (vibrance - 1.0))[:, :, np.newaxis]
        luma = (image @ _LUMA_BGR)[:, :, np.newaxis]
        boosted: np.ndarray = np.clip(luma + (image - luma) * factor, 0.0, 1.0)
        return boosted

    @_dtype_flexible
    def apply_green_removal(self, image: np.ndarray, amount: int) -> np.ndarray:
        """SCNR "average neutral" green removal (0-100).

        Green is capped at the mean of red and blue, blended in by ``amount``. A
        one-shot-colour sensor's residual green cast goes; a genuinely teal OIII
        filament (green *and* blue) keeps most of its colour, since blue lifts the
        cap along with it.
        """
        if amount <= 0:
            return image
        neutral = 0.5 * (image[:, :, 0] + image[:, :, 2])
        excess = np.clip(image[:, :, 1] - neutral, 0.0, None)
        out = image.copy()
        out[:, :, 1] -= (amount / 100.0) * excess
        return out

    @_dtype_flexible
    def apply_clarity(self, image: np.ndarray, clarity: float) -> np.ndarray:
        """Local contrast via unsharp mask; negative softens (-1.0..1.0)."""
        if _unchanged(clarity, 0.0):
            return image
        blurred = cv2.GaussianBlur(image, (0, 0), sigmaX=9)
        if clarity > 0:
            strength = clarity * 1.5
            out = cv2.addWeighted(image, 1.0 + strength, blurred, -strength, 0)
        else:
            strength = abs(clarity) * 0.5
            out = cv2.addWeighted(image, 1.0 - strength, blurred, strength, 0)
        return np.clip(out, 0.0, 1.0)

    @_dtype_flexible
    def apply_denoise(self, image: np.ndarray, denoise: int) -> np.ndarray:
        """Multiscale (starlet) luminance denoise (0 = off .. 100 = aggressive).

        The luma plane's four finest wavelet layers are shrunk at up to 3 noise
        sigma, following a local noise map - grain goes, while stars and
        filaments (coefficients far above the noise) keep their amplitude. A
        bilateral filter, the previous implementation, flattened faint stars and
        left a plastic texture. Colour is handled by `apply_chroma_denoise`.
        """
        if denoise <= 0:
            return image
        y, cr, cb = cv2.split(cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb))
        y = denoise_plane(y, _DENOISE_MAX_SIGMAS * denoise / 100.0, _DENOISE_LAYERS)
        out = cv2.cvtColor(cv2.merge([y, cr, cb]), cv2.COLOR_YCrCb2BGR)
        return np.clip(out, 0.0, 1.0)

    @_dtype_flexible
    def apply_chroma_denoise(self, image: np.ndarray, amount: int) -> np.ndarray:
        """Multiscale (starlet) denoise of just the colour (Cr/Cb) planes (0-100).

        Colour speckle is usually more objectionable than luma noise in a
        stacked astro frame, and can be smoothed much harder than luma
        without an apparent loss of detail, since detail lives almost
        entirely in luma - so it takes a harder cut, one layer deeper, than
        `apply_denoise`, and luma is left untouched.
        """
        if amount <= 0:
            return image
        y, cr, cb = cv2.split(cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb))
        cut = _CHROMA_DENOISE_MAX_SIGMAS * amount / 100.0
        cr = denoise_plane(cr, cut, _CHROMA_DENOISE_LAYERS, local=False)
        cb = denoise_plane(cb, cut, _CHROMA_DENOISE_LAYERS, local=False)
        out = cv2.cvtColor(cv2.merge([y, cr, cb]), cv2.COLOR_YCrCb2BGR)
        return np.clip(out, 0.0, 1.0)

    def apply_linear_denoise(self, image: np.ndarray, denoise: int) -> np.ndarray:
        """Starlet denoise of each plane of linear data (mono or RGB, ``float32``).

        The fallback when the DeepSNR engine was asked to run on a linear
        composite and failed: the same multiscale shrinkage as `apply_denoise`,
        per plane (the linear data has no meaningful luma/chroma split yet).
        """
        if denoise <= 0:
            return image
        cut = _DENOISE_MAX_SIGMAS * denoise / 100.0
        if image.ndim == 2:  # noqa: PLR2004
            return denoise_plane(image.astype(np.float32), cut, _DENOISE_LAYERS)
        planes = [
            denoise_plane(
                np.ascontiguousarray(image[..., c], dtype=np.float32), cut, _DENOISE_LAYERS
            )
            for c in range(image.shape[2])
        ]
        return np.stack(planes, axis=-1)

    def classic_starless_split(
        self, image: np.ndarray, sensitivity: int, max_size: int, removal_amount: int
    ) -> tuple[np.ndarray, np.ndarray]:
        """:meth:`StarlessService.split` for a BGR ``float32`` image.

        The classical split is uint8-native (mask units, the detector), so it
        round-trips at this boundary; the StarNet2 engine does not.
        """
        starless, removed = self._starless.split(
            _to_u8(image), sensitivity, max_size, removal_amount
        )
        return _to_f32(starless), _to_f32(removed)

    @_dtype_flexible
    def apply_star_reduction(
        self, image: np.ndarray, amount: int, sensitivity: int = 50, max_size: int = 30
    ) -> np.ndarray:
        """Shrink individually-detected stars to emphasise the DSO.

        Each star is located by :class:`StarDetectionService` (per-star blob
        detection) rather than a single image-wide mask, so only genuine
        compact bright points are touched - diffuse nebulosity is never
        dimmed, unlike the old global top-hat blend. Inside each star's own
        soft-edged footprint, the image is blended toward an eroded, slightly
        darkened copy of itself - erosion genuinely shrinks the bright disc
        while keeping the star's own colour and texture, unlike a flat
        `cv2.inpaint` fill (an earlier version), which produced oversized,
        textureless pale blobs instead of a smaller star. The eroded fill is
        floored at :meth:`StarDetectionService.local_background` (the image
        with stars morphologically opened away) so it can never crush below
        what the real surrounding sky/nebulosity looks like - erosion alone
        can push a small isolated star toward its darkest neighbour, which
        for a star on a dark sky is near-zero, and was a visible black dot at
        full strength before this floor was added. ``amount``: 0 = off .. 100
        = strong. ``sensitivity`` / ``max_size`` (0-100) tune what counts as a
        star; see :meth:`StarDetectionService.detect`.
        """
        if amount <= 0:
            return image
        strength = amount / 100.0

        u8 = _to_u8(image)
        stars = self._star_detector.detect(u8, sensitivity, max_size)
        if not stars:
            return image

        height, width = image.shape[:2]
        star_mask = np.zeros((height, width), dtype=np.float32)
        for star in stars:
            cv2.circle(
                star_mask,
                (round(star.x), round(star.y)),
                max(1, round(star.radius * _STAR_FALLOFF_MARGIN)),
                1.0,
                thickness=-1,
            )
        star_mask = cast("np.ndarray", cv2.GaussianBlur(star_mask, (0, 0), sigmaX=1.2))
        weight = np.clip(star_mask * (0.4 + 0.6 * strength), 0.0, 1.0)[:, :, np.newaxis]

        small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        eroded = cv2.erode(image, small, iterations=1 + round(strength * 3)).astype(np.float32)
        eroded *= 1.0 - 0.6 * strength

        local_background = _to_f32(self._star_detector.local_background(u8, max_size))
        reduced = np.maximum(eroded, local_background)

        blended = image * (1.0 - weight) + reduced * weight
        return cast("np.ndarray", np.clip(blended, 0.0, 1.0))

    @_dtype_flexible
    def apply_sharpness(self, image: np.ndarray, sharpness: float) -> np.ndarray:
        """Blur below 1.0, noise-aware multiscale sharpen above (0.0..2.0).

        Above 1.0 the two finest starlet layers of the luma plane are boosted, but
        only where they rise clearly above the noise (`enhance_detail`), so stars
        and fine filaments sharpen while the background grain is not amplified,
        and colour is left alone (no coloured fringes).
        """
        if _unchanged(sharpness, 1.0):
            return image
        if sharpness < 1.0:
            radius = round((1.0 - sharpness) * 8) * 2 + 1
            return cast("np.ndarray", cv2.GaussianBlur(image, (radius, radius), 0))
        y, cr, cb = cv2.split(cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb))
        y = enhance_detail(y, (sharpness - 1.0) * _SHARPEN_GAIN, _SHARPEN_LAYERS)
        out = cv2.cvtColor(cv2.merge([y, cr, cb]), cv2.COLOR_YCrCb2BGR)
        return np.clip(out, 0.0, 1.0)

    @_dtype_flexible
    def apply_look(
        self, image: np.ndarray, look: LookParameters, sky_mask: np.ndarray | None = None
    ) -> np.ndarray:
        """The optional "Style" finishing look (``app.services.looks``); identity when none.

        ``sky_mask`` (0..1, already through this edit's geometry) lets a
        night-landscape look treat the sky and the foreground apart.
        """
        return self._looks.apply(image, look, sky_mask)

    def _background_stages(
        self, params: ProcessingParameters
    ) -> list[tuple[str, Callable[[np.ndarray], np.ndarray]]]:
        """Geometry + the sky/optics corrections - these belong on the whole
        frame (stars included), so they run before any starless split."""
        return [
            ("geometry", lambda r: self.apply_geometry(r, params.geometry)),
            (
                "color_correction",
                lambda r: self.apply_white_balance(r, params.temperature, params.tint),
            ),
            ("green_removal", lambda r: self.apply_green_removal(r, params.green_removal)),
            (
                "vignette_correction",
                lambda r: self.apply_vignette_correction(r, params.vignette_correction),
            ),
            (
                "gradient_reduction",
                lambda r: self.apply_gradient_reduction(r, params.gradient_reduction),
            ),
            ("dehaze", lambda r: self.apply_dehaze(r, params.dehaze)),
        ]

    def _creative_stages(
        self, params: ProcessingParameters
    ) -> list[tuple[str, Callable[[np.ndarray], np.ndarray]]]:
        """Tone, colour, and detail work - runs on the starless image when star
        removal is active, so the nebula can be pushed without bloating stars."""
        return [
            ("contrast", lambda r: self.apply_contrast(r, params.contrast)),
            ("exposure", lambda r: self.apply_exposure(r, params.exposure)),
            (
                "highlights_shadows",
                lambda r: self.apply_highlights_shadows(r, params.highlights, params.shadows),
            ),
            (
                "whites_blacks",
                lambda r: self.apply_whites_blacks(r, params.whites, params.blacks),
            ),
            ("tone_curve", lambda r: self.apply_tone_curve(r, params.curve_points)),
            (
                "channel_curves",
                lambda r: self.apply_channel_curves(
                    r, params.red_curve_points, params.green_curve_points, params.blue_curve_points
                ),
            ),
            ("saturation", lambda r: self.apply_saturation(r, params.saturation)),
            ("vibrance", lambda r: self.apply_vibrance(r, params.vibrance)),
            ("clarity", lambda r: self.apply_clarity(r, params.clarity)),
            ("denoise", lambda r: self.apply_denoise(r, params.denoise)),
            ("chroma_denoise", lambda r: self.apply_chroma_denoise(r, params.chroma_denoise)),
            (
                "star_reduction",
                lambda r: self.apply_star_reduction(
                    r, params.star_reduction, params.star_sensitivity, params.star_max_size
                ),
            ),
            ("sharpness", lambda r: self.apply_sharpness(r, params.sharpness)),
        ]

    def apply_parameters(
        self,
        image: np.ndarray,
        params: ProcessingParameters,
        on_step: StepCallback | None = None,
        *,
        linear_composite: bool = False,
        starless_split: StarlessSplitFn | None = None,
        denoise_stage: DenoiseStageFn | None = None,
        sky_mask: np.ndarray | None = None,
        render_hints: RenderHints | None = None,
    ) -> np.ndarray:
        """Run the full pipeline in the recommended order.

        Returns the input unchanged when every parameter is at its default.
        ``on_step(step_name, percent)`` is called as each stage begins.

        When ``star_removal`` is set, the pipeline splits after the background
        corrections: the stars are pulled out, every creative stage runs on the
        starless image, and ``star_recombine`` screen-blends the removed star flux
        back at the end. ``star_removal = 0`` (the default) is byte-identical to
        the flat pipeline. The split defaults to the classical
        ``StarlessService.split``; ``starless_split`` overrides it with an
        alternative backend of the same shape (the StarNet2 engine - see
        ``app.services.external_starless``), which the caller has already vetted
        and wrapped with its own fallback.

        ``denoise_stage``: when given (the DeepSNR engine - see
        ``app.services.external_denoise``), the classical ``denoise`` creative
        stage is dropped so denoise never runs twice, and the engine runs instead
        - on a stacked composite, on the **linear** data ahead of ``stack_base``
        (before any stretch amplifies and reshapes the noise, which is what the
        model is trained on); on an ordinary image, right after the background
        corrections. Like ``starless_split``, the caller has vetted it and wrapped
        its fallback. Both engines exchange 16-bit or float data, never 8-bit.

        ``linear_composite``: ``image`` is a linear stacked composite (RGB
        planes, ``float32``), not a uint8 upload - prepend the ``stack_base``
        pre-stage (background extraction, colour calibration and the tunable
        stretch, all from ``params.stack``) which turns it into the BGR
        ``float32`` the rest of the pipeline expects. ``sky_mask`` (a
        nightscape composite's sky mask) and ``render_hints`` (what its source
        frames say - see :class:`RenderHints`) are handed to that pre-stage.

        ``params.look`` is **not** applied here: the "Style" look is a final
        layer on this method's 8-bit result, applied by :meth:`apply_look`, so
        the caller can keep the pre-look result (to re-render only the look, to
        build the gallery thumbnails, or to export without it).
        """
        background = self._background_stages(params)
        creative = self._creative_stages(params)
        if linear_composite:
            background = [
                (
                    "stack_base",
                    lambda r: render_stack_base(r, params.stack, sky_mask, render_hints),
                ),
                *background,
            ]
        if denoise_stage is not None:
            # DeepSNR takes over the classical `denoise` slot; drop it so denoise
            # never runs twice.
            deepsnr = denoise_stage
            if linear_composite:
                background = [("denoise", lambda r: deepsnr(r, True)), *background]
            else:
                background = [*background, ("denoise", lambda r: deepsnr(r, False))]
            creative = [(name, stage) for name, stage in creative if name != "denoise"]

        if params.star_removal <= 0:
            stages = background + creative
        else:
            split_impl = starless_split or self.classic_starless_split
            stars_layer: list[np.ndarray] = []

            def split(r: np.ndarray) -> np.ndarray:
                starless, removed = split_impl(
                    r, params.star_sensitivity, params.star_max_size, params.star_removal
                )
                stars_layer.append(removed)
                return starless

            def recombine(r: np.ndarray) -> np.ndarray:
                return self._starless.recombine(r, stars_layer[0], params.star_recombine)

            stages = [
                *background,
                ("star_removal", split),
                *creative,
                ("star_recombine", recombine),
            ]

        result = _to_f32(image) if image.dtype == np.uint8 else image.astype(np.float32)
        for index, (name, stage) in enumerate(stages):
            if on_step is not None:
                on_step(name, round(10 + index * 80 / len(stages)))
            result = stage(result)
        return _to_u8(result)
