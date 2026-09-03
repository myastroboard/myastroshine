"""ImageProcessingService - the single-image enhancement pipeline.

Algorithm details and the recommended operation order live in docs/ALGORITHMS.md.
Every method takes and returns a BGR ``uint8`` numpy array. Each is an identity
transform when its parameter sits at the default value.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.logging_config import get_logger
from app.models import ProcessingParameters
from app.utils.math_utils import kelvin_to_rgb_gain, tint_to_rgb_gain, to_uint8

logger = get_logger(__name__)

_EPS = 1e-3  # a parameter within this of its default is treated as "unchanged"
_NEUTRAL_KELVIN = 6500
_DENOISE_MORPH_THRESHOLD = 50


def _unchanged(value: float, default: float) -> bool:
    return abs(value - default) < _EPS


class ImageProcessingService:
    """Applies enhancement parameters to an image."""

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

    def apply_parameters(self, image: np.ndarray, params: ProcessingParameters) -> np.ndarray:
        """Run the full pipeline in the recommended order.

        Returns the input unchanged when every parameter is at its default.
        """
        result = image
        result = self.apply_white_balance(result, params.temperature, params.tint)
        result = self.apply_contrast(result, params.contrast)
        result = self.apply_brightness(result, params.brightness)
        result = self.apply_highlights_shadows(result, params.highlights, params.shadows)
        result = self.apply_saturation(result, params.saturation)
        result = self.apply_vibrance(result, params.vibrance)
        result = self.apply_clarity(result, params.clarity)
        result = self.apply_denoise(result, params.denoise)
        result = self.apply_sharpness(result, params.sharpness)
        return result
