"""StarDetectionService algorithm tests."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.services.star_detection import StarDetectionService


@pytest.fixture
def detector() -> StarDetectionService:
    return StarDetectionService()


def _synthetic_field() -> tuple[np.ndarray, list[tuple[int, int]]]:
    """A dark field with 5 small, sharp stars and one large, smooth glow."""
    image = np.zeros((200, 200, 3), dtype=np.uint8)
    # Diffuse "nebula" core: large and smoothly varying, should not read as a star.
    cv2.circle(image, (100, 100), 40, (90, 90, 100), -1)
    image = cv2.GaussianBlur(image, (0, 0), sigmaX=14).astype(np.uint8)

    stars = [(20, 20), (180, 20), (20, 180), (180, 180), (100, 30)]
    for x, y in stars:
        cv2.circle(image, (x, y), 2, (255, 255, 255), -1)
    return image, stars


def test_no_bright_features_detects_nothing(detector: StarDetectionService) -> None:
    """A flat, dim image has nothing for the top-hat pre-filter to isolate."""
    image = np.full((100, 100, 3), 20, dtype=np.uint8)
    assert detector.detect(image, sensitivity=50, max_size=30) == []


def test_detects_each_star_and_skips_the_diffuse_core(detector: StarDetectionService) -> None:
    """Every planted star is found near its true position; the glow is not."""
    image, stars = _synthetic_field()
    found = detector.detect(image, sensitivity=70, max_size=30)

    assert len(found) == len(stars)
    for x, y in stars:
        assert any(abs(star.x - x) < 3 and abs(star.y - y) < 3 for star in found)
    # The nebula core sits at (100, 100); no detection should land near it.
    assert not any(abs(star.x - 100) < 10 and abs(star.y - 100) < 10 for star in found)


def test_higher_sensitivity_detects_at_least_as_many_stars(
    detector: StarDetectionService,
) -> None:
    """Raising sensitivity lowers the detection threshold - never fewer stars."""
    image, _ = _synthetic_field()
    low = detector.detect(image, sensitivity=5, max_size=30)
    high = detector.detect(image, sensitivity=95, max_size=30)
    assert len(high) >= len(low)


def test_detected_radius_is_positive_and_bounded(detector: StarDetectionService) -> None:
    image, _stars = _synthetic_field()
    found = detector.detect(image, sensitivity=70, max_size=30)
    assert found
    for star in found:
        assert 0 < star.radius < 30
