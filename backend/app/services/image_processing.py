"""ImageProcessingService - the single-image enhancement pipeline.

Algorithm details and the recommended operation order live in docs/ALGORITHMS.md.
Every method takes and returns a BGR ``uint8`` numpy array. Each is an identity
transform when its parameter sits at the default value.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import cast

import cv2
import numpy as np

from app.logging_config import get_logger
from app.models import CurvePoint, GeometryParameters, ProcessingParameters
from app.services.star_detection import StarDetectionService
from app.utils.math_utils import (
    curve_points_to_lut,
    kelvin_to_rgb_gain,
    tint_to_rgb_gain,
    to_uint8,
)

StepCallback = Callable[[str, int], None]

logger = get_logger(__name__)

_EPS = 1e-3  # a parameter within this of its default is treated as "unchanged"
_NEUTRAL_KELVIN = 6500
_DENOISE_MORPH_THRESHOLD = 50
_STAR_FALLOFF_MARGIN = 1.6  # widen each star's blend footprint past its own radius
_DEHAZE_PATCH_SIZE = 15
_DEHAZE_ATMOSPHERE_FRACTION = 0.001  # brightest 0.1% of dark-channel pixels
_DEHAZE_MIN_ATMOSPHERIC_LIGHT = 0.2  # floor, so a very dark frame can't push this near zero
_DEHAZE_ESTIMATE_MAX_SIZE = 800  # dark-channel/transmission map; recovery itself runs at full res
_GRADIENT_ESTIMATE_MAX_SIZE = 256  # the background is smooth/low-frequency - a small copy is enough
_VIGNETTE_ESTIMATE_MAX_SIZE = 128  # the gain map depends only on position, not image content


def _unchanged(value: float, default: float) -> bool:
    return abs(value - default) < _EPS


class ImageProcessingService:
    """Applies enhancement parameters to an image."""

    def __init__(self) -> None:
        self._star_detector = StarDetectionService()

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

    def apply_white_balance(self, image: np.ndarray, temperature: int, tint: int) -> np.ndarray:
        """Adjust colour temperature (2000-8000K, 6500 neutral) and tint (-50..50)."""
        if temperature == _NEUTRAL_KELVIN and tint == 0:
            return image
        r_gain, g_gain, b_gain = kelvin_to_rgb_gain(temperature)
        r_tint, g_tint, b_tint = tint_to_rgb_gain(tint)
        # image is BGR, so order the gains B, G, R.
        gains = np.array([b_gain * b_tint, g_gain * g_tint, r_gain * r_tint], dtype=np.float32)
        return to_uint8(image.astype(np.float32) * gains)

    def apply_vignette_correction(self, image: np.ndarray, amount: int) -> np.ndarray:
        """Brighten toward the corners to counteract lens vignetting (0-100).

        A generic radial gain model, not a per-lens calibrated profile -
        nothing here knows what lens took the shot. Gain grows with squared
        distance from the image centre, capped so even at full strength the
        corners gain at most 80%. The gain map depends only on position, not
        image content, so (like `apply_gradient_reduction`) it's computed on a
        small downscaled grid and resized up - full-resolution precision
        would be wasted work for a smooth analytic function.
        """
        if amount <= 0:
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
        return to_uint8(image.astype(np.float32) * gain[:, :, np.newaxis])

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
        return to_uint8(image.astype(np.float32) - correction)

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
        img = image.astype(np.float32) / 255.0
        height, width = image.shape[:2]
        scale = _DEHAZE_ESTIMATE_MAX_SIZE / max(height, width)
        small = (
            cv2.resize(
                image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA
            ).astype(np.float32)
            / 255.0
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
        return to_uint8(np.clip(recovered, 0.0, 1.0) * 255.0)

    def apply_contrast(self, image: np.ndarray, contrast: float) -> np.ndarray:
        """Linear stretch about the image mean, with a gentle gamma (0.5..3.0)."""
        if _unchanged(contrast, 1.0):
            return image
        img = image.astype(np.float32) / 255.0
        mean = float(img.mean())
        stretched = (img - mean) * contrast + mean
        gamma = 1.0 / max(1.0 + (contrast - 1.0) * 0.1, 0.5)
        stretched = np.power(np.clip(stretched, 0.0, 1.0), gamma)
        return to_uint8(stretched * 255.0)

    def apply_exposure(self, image: np.ndarray, exposure: float) -> np.ndarray:
        """Offset overall luminance (-1.0..1.0), scaled to +/- 50 levels."""
        if _unchanged(exposure, 0.0):
            return image
        return to_uint8(image.astype(np.float32) + exposure * 50.0)

    def apply_highlights_shadows(
        self, image: np.ndarray, highlights: float, shadows: float
    ) -> np.ndarray:
        """Recover bright / dark detail via luminance-masked tone curves (-1.0..1.0)."""
        if _unchanged(highlights, 0.0) and _unchanged(shadows, 0.0):
            return image
        img = image.astype(np.float32) / 255.0
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        highlight_mask = np.square(gray)[:, :, np.newaxis]
        shadow_mask = np.square(1.0 - gray)[:, :, np.newaxis]
        img = img + highlight_mask * highlights * 0.3 + shadow_mask * shadows * 0.3
        return to_uint8(img * 255.0)

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
        img = image.astype(np.float32) / 255.0
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        # np.square(np.square(x)) (x**4 via repeated squaring) is a fast path;
        # np.power(x, 4) is not - measurably so at 24MP.
        white_mask = np.square(np.square(gray))[:, :, np.newaxis]
        black_mask = np.square(np.square(1.0 - gray))[:, :, np.newaxis]
        img = img + white_mask * whites * 0.4 + black_mask * blacks * 0.4
        return to_uint8(img * 255.0)

    def apply_tone_curve(self, image: np.ndarray, curve_points: list[CurvePoint]) -> np.ndarray:
        """Apply a user-drawn tone curve as a 256-entry LUT, identical on each channel.

        ``curve_points`` are ``(x, y)`` 8-bit input/output pairs spanning
        0-255; empty means no curve (identity). See
        :func:`app.utils.math_utils.curve_points_to_lut` for the interpolation.
        """
        if not curve_points:
            return image
        lut = curve_points_to_lut([(point.x, point.y) for point in curve_points])
        return cast("np.ndarray", cv2.LUT(image, lut))

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
        blue, green, red = cv2.split(image)
        if blue_curve_points:
            blue = cv2.LUT(blue, curve_points_to_lut([(p.x, p.y) for p in blue_curve_points]))
        if green_curve_points:
            green = cv2.LUT(green, curve_points_to_lut([(p.x, p.y) for p in green_curve_points]))
        if red_curve_points:
            red = cv2.LUT(red, curve_points_to_lut([(p.x, p.y) for p in red_curve_points]))
        return cast("np.ndarray", cv2.merge([blue, green, red]))

    def apply_saturation(self, image: np.ndarray, saturation: float) -> np.ndarray:
        """Scale the HSV saturation channel (0.0..2.0)."""
        if _unchanged(saturation, 1.0):
            return image
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[:, :, 1] = np.clip(hsv[:, :, 1] * saturation, 0, 255)
        return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    def apply_vibrance(self, image: np.ndarray, vibrance: float) -> np.ndarray:
        """Boost saturation weighted towards less-saturated pixels (0.0..2.0)."""
        if _unchanged(vibrance, 1.0):
            return image
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)
        sat = hsv[:, :, 1] / 255.0
        boost = (1.0 - sat) * (vibrance - 1.0)
        hsv[:, :, 1] = np.clip(hsv[:, :, 1] * (1.0 + boost), 0, 255)
        return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    def apply_clarity(self, image: np.ndarray, clarity: float) -> np.ndarray:
        """Local contrast via unsharp mask; negative softens (-1.0..1.0)."""
        if _unchanged(clarity, 0.0):
            return image
        blurred = cv2.GaussianBlur(image, (0, 0), sigmaX=9)
        if clarity > 0:
            strength = clarity * 1.5
            return cv2.addWeighted(image, 1.0 + strength, blurred, -strength, 0)
        strength = abs(clarity) * 0.5
        return cv2.addWeighted(image, 1.0 - strength, blurred, strength, 0)

    def apply_denoise(self, image: np.ndarray, denoise: int) -> np.ndarray:
        """Edge-preserving bilateral filter (0 = off .. 100 = aggressive)."""
        if denoise <= 0:
            return image
        strength = denoise / 100.0
        diameter = int(5 + strength * 10)
        sigma = 40.0 + strength * 60.0
        out = cv2.bilateralFilter(image, diameter, sigma, sigma)
        if denoise > _DENOISE_MORPH_THRESHOLD:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, kernel)
        return out

    def apply_chroma_denoise(self, image: np.ndarray, amount: int) -> np.ndarray:
        """Bilateral-filter just the colour (Cr/Cb) channels, leaving luma untouched (0-100).

        Colour speckle is usually more objectionable than luma noise in a
        stacked astro frame, and can be smoothed much harder than luma
        without an apparent loss of detail, since detail lives almost
        entirely in luma. Same diameter/sigma mapping as `apply_denoise`,
        applied per chroma channel.
        """
        if amount <= 0:
            return image
        strength = amount / 100.0
        diameter = int(5 + strength * 10)
        sigma = 40.0 + strength * 60.0
        y, cr, cb = cv2.split(cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb))
        cr = cv2.bilateralFilter(cr, diameter, sigma, sigma)
        cb = cv2.bilateralFilter(cb, diameter, sigma, sigma)
        return cast("np.ndarray", cv2.cvtColor(cv2.merge([y, cr, cb]), cv2.COLOR_YCrCb2BGR))

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

        stars = self._star_detector.detect(image, sensitivity, max_size)
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

        local_background = self._star_detector.local_background(image, max_size).astype(np.float32)
        reduced = np.maximum(eroded, local_background)

        blended = image.astype(np.float32) * (1.0 - weight) + reduced * weight
        return to_uint8(blended)

    def apply_sharpness(self, image: np.ndarray, sharpness: float) -> np.ndarray:
        """Blur below 1.0, Laplacian-kernel sharpen above (0.0..2.0)."""
        if _unchanged(sharpness, 1.0):
            return image
        if sharpness < 1.0:
            radius = round((1.0 - sharpness) * 8) * 2 + 1
            return cv2.GaussianBlur(image, (radius, radius), 0)
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
        sharp = cv2.filter2D(image, -1, kernel)
        strength = (sharpness - 1.0) * 0.5
        return cv2.addWeighted(image, 1.0 - strength, sharp, strength, 0)

    def apply_parameters(
        self,
        image: np.ndarray,
        params: ProcessingParameters,
        on_step: StepCallback | None = None,
    ) -> np.ndarray:
        """Run the full pipeline in the recommended order.

        Returns the input unchanged when every parameter is at its default.
        ``on_step(step_name, percent)`` is called as each stage begins.
        """
        stages: list[tuple[str, Callable[[np.ndarray], np.ndarray]]] = [
            ("geometry", lambda r: self.apply_geometry(r, params.geometry)),
            (
                "color_correction",
                lambda r: self.apply_white_balance(r, params.temperature, params.tint),
            ),
            (
                "vignette_correction",
                lambda r: self.apply_vignette_correction(r, params.vignette_correction),
            ),
            (
                "gradient_reduction",
                lambda r: self.apply_gradient_reduction(r, params.gradient_reduction),
            ),
            ("dehaze", lambda r: self.apply_dehaze(r, params.dehaze)),
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

        result = image
        for index, (name, stage) in enumerate(stages):
            if on_step is not None:
                on_step(name, round(10 + index * 80 / len(stages)))
            result = stage(result)
        return result
