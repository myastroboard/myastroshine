"""AutoAstroService heuristic tests."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.services.auto_astro import AutoAstroService
from app.services.star_detection import StarDetectionService


@pytest.fixture
def service() -> AutoAstroService:
    return AutoAstroService(StarDetectionService())


def _jpeg_roundtrip(image: np.ndarray) -> np.ndarray:
    """Match what a real upload looks like by the time it's analysed.

    Every session's original is JPEG-encoded on save (`image_utils.save_image`),
    which correlates pixel noise across each 8x8 DCT block. Raw i.i.d. per-pixel
    noise (e.g. straight from `rng.integers`) is *not* representative of that -
    it's far denser and uncorrelated, and unrealistically trips the star
    detector's noise-vs-signal threshold. Round-tripping through JPEG here
    keeps this test's input honest to what `AutoAstroService` actually sees.
    """
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])
    assert ok
    decoded = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    assert decoded is not None
    return decoded


def test_washed_out_frame_gets_stretched(service: AutoAstroService) -> None:
    """A narrow, mid-grey histogram should be pulled toward using the full range.

    Deliberately doesn't assert anything about `star_reduction` here: a frame
    that's *purely* flat plus noise (no real signal at all to compete against
    it) is an adversarial worst case for any point-source detector, not a
    realistic "washed out" astrophoto - real underexposed frames still have
    actual stars as their brightest points. That "no false stars on a clean,
    starless, but structured frame" property is `test_well_exposed_starless_
    frame_stays_near_default` below.
    """
    rng = np.random.default_rng(1)
    image = np.full((200, 200, 3), 130, dtype=np.uint8)
    noise = rng.integers(-15, 15, image.shape, dtype=np.int16)
    image = np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    image = _jpeg_roundtrip(image)

    params = service.suggest_parameters(image)

    assert params.contrast > 1.2


def test_well_exposed_starless_frame_stays_near_default(service: AutoAstroService) -> None:
    """A frame that already spans the full range shouldn't be pushed hard.

    Includes light, JPEG-realistic noise (not a perfectly clean synthetic
    gradient) so this also stands as the "no false stars on a real but
    starless frame" regression check.
    """
    rng = np.random.default_rng(3)
    image = np.zeros((200, 200, 3), dtype=np.uint8)
    image[:, :] = np.linspace(0, 255, 200, dtype=np.uint8)[np.newaxis, :, np.newaxis]
    noise = rng.integers(-6, 6, image.shape, dtype=np.int16)
    image = np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    image = _jpeg_roundtrip(image)

    params = service.suggest_parameters(image)

    assert 0.5 <= params.contrast <= 1.5
    assert params.star_reduction == 0


def test_busy_star_field_suggests_star_reduction(service: AutoAstroService) -> None:
    """Many small bright points should raise the suggested star_reduction."""
    rng = np.random.default_rng(2)
    image = np.zeros((300, 300, 3), dtype=np.uint8)
    image[:, :] = 30
    for _ in range(200):
        y, x = int(rng.integers(0, 300)), int(rng.integers(0, 300))
        cv2.circle(image, (x, y), 2, (255, 255, 255), -1)

    params = service.suggest_parameters(image)

    assert params.star_reduction > 0
    assert params.star_reduction <= 60


def test_flat_degenerate_frame_skips_tone_changes(service: AutoAstroService) -> None:
    """A perfectly flat frame has no usable range to stretch - stay at defaults."""
    image = np.full((100, 100, 3), 128, dtype=np.uint8)

    params = service.suggest_parameters(image)

    assert params.contrast == 1.0
    assert params.exposure == 0.0
    assert params.highlights == 0.0
    assert params.shadows == 0.0
