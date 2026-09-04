"""Fixtures for the opt-in performance benchmark suite (see test_*.py docstrings)."""

from __future__ import annotations

import numpy as np
import pytest

# A common full-frame/APS-C camera resolution (~24MP) - representative of a real
# astrophotography JPEG upload, not the tiny fixtures the rest of the suite uses.
FULL_RES_SIZE = (4000, 6000)  # (height, width)

# app_settings.py's preview_max_size default (see app/utils/app_settings.py).
PREVIEW_SIZE = (512, 512)


def _synthetic_astro_image(height: int, width: int, *, seed: int) -> np.ndarray:
    """A BGR frame with gradient + colour blocks + bright points, at real
    processing cost: enough structure that denoise/star-reduction/clarity all
    do real work, unlike a uniform or all-zero array."""
    rng = np.random.default_rng(seed)
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :, 0] = np.linspace(0, 255, width, dtype=np.uint8)  # blue ramp
    image[: height // 2, :, 2] = 180  # red block, top half
    image[height // 2 :, :, 1] = 140  # green block, bottom half
    noise = rng.integers(-12, 12, image.shape, dtype=np.int16)
    image = np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    star_count = max(50, (height * width) // 40_000)
    for _ in range(star_count):
        y, x = int(rng.integers(0, height)), int(rng.integers(0, width))
        radius = int(rng.integers(1, 5))
        brightness = int(rng.integers(180, 255))
        cv2_circle(image, (x, y), radius, brightness)
    return image


def cv2_circle(image: np.ndarray, center: tuple[int, int], radius: int, brightness: int) -> None:
    import cv2

    cv2.circle(image, center, radius, (brightness, brightness, brightness), -1)


@pytest.fixture(scope="module")
def full_res_image() -> np.ndarray:
    """~24MP synthetic frame - the "full-res enhance < 5s" acceptance criterion."""
    return _synthetic_astro_image(*FULL_RES_SIZE, seed=100)


@pytest.fixture(scope="module")
def preview_image() -> np.ndarray:
    """512px synthetic frame - the "slider response < 500ms" acceptance criterion."""
    return _synthetic_astro_image(*PREVIEW_SIZE, seed=101)
