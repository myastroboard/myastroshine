"""ImageProcessingService - the single-image enhancement pipeline.

Algorithm details and the recommended operation order live in docs/ALGORITHMS.md.
Every method takes and returns a BGR ``uint8`` numpy array. Each is an identity
transform when its parameter sits at the default value.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import cv2
import numpy as np

from app.logging_config import get_logger
from app.models import GeometryParameters, ProcessingParameters
from app.utils.math_utils import kelvin_to_rgb_gain, tint_to_rgb_gain, to_uint8

StepCallback = Callable[[str, int], None]

logger = get_logger(__name__)

_EPS = 1e-3  # a parameter within this of its default is treated as "unchanged"
_NEUTRAL_KELVIN = 6500
_DENOISE_MORPH_THRESHOLD = 50
_STAR_KERNEL_SIZE = 9  # px; compact bright features up to this size read as stars


def _unchanged(value: float, default: float) -> bool:
    return abs(value - default) < _EPS


class ImageProcessingService:
    """Applies enhancement parameters to an image."""

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

    def apply_brightness(self, image: np.ndarray, brightness: float) -> np.ndarray:
        """Offset luminance (-1.0..1.0), scaled to +/- 50 levels."""
        if _unchanged(brightness, 0.0):
            return image
        return to_uint8(image.astype(np.float32) + brightness * 50.0)

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

    def apply_star_reduction(self, image: np.ndarray, amount: int) -> np.ndarray:
        """Shrink and dim compact bright points (stars) to emphasise the DSO.

        Stars are isolated with a white top-hat: small bright features on a
        smoothly varying background. Diffuse nebulosity varies slowly, so the
        top-hat leaves it near zero and it stays out of the mask. Inside the
        mask the image is blended toward an eroded, slightly darkened copy, so
        star disks contract while the object is untouched. 0 = off .. 100 = strong.
        """
        if amount <= 0:
            return image
        strength = amount / 100.0

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (_STAR_KERNEL_SIZE, _STAR_KERNEL_SIZE)
        )
        tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel).astype(np.float32)
        peak = float(tophat.max())
        if peak < 1.0:
            return image

        mask = np.clip(tophat / peak, 0.0, 1.0)
        # Grow then feather so star cores keep full weight after blurring.
        grown = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
        mask = cv2.GaussianBlur(np.sqrt(np.maximum(mask, grown)), (0, 0), sigmaX=1.2)
        weight = np.clip(mask * (0.4 + 0.6 * strength), 0.0, 1.0)[:, :, np.newaxis]

        small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        reduced = cv2.erode(image, small, iterations=1 + round(strength * 3)).astype(np.float32)
        reduced *= 1.0 - 0.6 * strength

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
            ("contrast", lambda r: self.apply_contrast(r, params.contrast)),
            ("brightness", lambda r: self.apply_brightness(r, params.brightness)),
            (
                "highlights_shadows",
                lambda r: self.apply_highlights_shadows(r, params.highlights, params.shadows),
            ),
            ("saturation", lambda r: self.apply_saturation(r, params.saturation)),
            ("vibrance", lambda r: self.apply_vibrance(r, params.vibrance)),
            ("clarity", lambda r: self.apply_clarity(r, params.clarity)),
            ("denoise", lambda r: self.apply_denoise(r, params.denoise)),
            ("star_reduction", lambda r: self.apply_star_reduction(r, params.star_reduction)),
            ("sharpness", lambda r: self.apply_sharpness(r, params.sharpness)),
        ]

        result = image
        for index, (name, stage) in enumerate(stages):
            if on_step is not None:
                on_step(name, round(10 + index * 80 / len(stages)))
            result = stage(result)
        return result
