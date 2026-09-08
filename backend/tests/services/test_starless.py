"""StarlessService algorithm tests (v0.3 star removal + recombination)."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.services.star_detection import StarDetectionService
from app.services.starless import StarlessService


@pytest.fixture
def service() -> StarlessService:
    return StarlessService(StarDetectionService())


def _nebula_with_stars() -> tuple[np.ndarray, list[tuple[int, int]]]:
    """A smooth mid-tone nebula glow with sharp white stars planted on top."""
    image = np.zeros((200, 200, 3), dtype=np.uint8)
    cv2.circle(image, (100, 100), 55, (70, 60, 90), -1)
    image = cv2.GaussianBlur(image, (0, 0), sigmaX=20).astype(np.uint8)
    stars = [(30, 30), (170, 35), (40, 165), (165, 170), (100, 40), (60, 110)]
    for x, y in stars:
        cv2.circle(image, (x, y), 2, (255, 255, 255), -1)
    return image, stars


def _star_brightness(image: np.ndarray, points: list[tuple[int, int]]) -> float:
    return float(np.mean([image[y, x].astype(int).sum() for x, y in points]))


def test_split_with_no_stars_is_a_noop(service: StarlessService) -> None:
    flat = np.full((80, 80, 3), 30, dtype=np.uint8)
    starless, stars_layer = service.split(flat, sensitivity=50, max_size=30, removal_amount=100)
    assert np.array_equal(starless, flat)
    assert not stars_layer.any()


def test_split_removes_stars_but_keeps_the_nebula(service: StarlessService) -> None:
    image, stars = _nebula_with_stars()
    before = _star_brightness(image, stars)
    core_before = int(image[100, 100].astype(int).sum())

    starless, _ = service.split(image, sensitivity=70, max_size=30, removal_amount=100)

    assert starless.shape == image.shape
    assert starless.dtype == np.uint8
    assert _star_brightness(starless, stars) < before * 0.5  # stars substantially gone
    assert int(starless[100, 100].astype(int).sum()) >= core_before * 0.9  # nebula core intact


def test_stars_layer_isolates_the_removed_flux(service: StarlessService) -> None:
    image, stars = _nebula_with_stars()
    _starless, stars_layer = service.split(image, sensitivity=70, max_size=30, removal_amount=100)

    assert _star_brightness(stars_layer, stars) > 200  # bright where stars were
    away_from_stars = stars_layer[95:105, 20:30]  # a nebula-only patch, no star nearby
    assert int(away_from_stars.max()) < 25  # ...and near-black elsewhere


def test_removal_amount_scales_the_effect(service: StarlessService) -> None:
    image, stars = _nebula_with_stars()
    before = _star_brightness(image, stars)
    full, _ = service.split(image, sensitivity=70, max_size=30, removal_amount=100)
    partial, _ = service.split(image, sensitivity=70, max_size=30, removal_amount=40)
    assert _star_brightness(full, stars) < _star_brightness(partial, stars) < before


def test_recombine_zero_returns_starless_untouched(service: StarlessService) -> None:
    image, _ = _nebula_with_stars()
    starless, stars_layer = service.split(image, sensitivity=70, max_size=30, removal_amount=100)
    assert np.array_equal(service.recombine(starless, stars_layer, 0), starless)


def test_recombine_brings_stars_back(service: StarlessService) -> None:
    image, stars = _nebula_with_stars()
    starless, stars_layer = service.split(image, sensitivity=70, max_size=30, removal_amount=100)

    faint = service.recombine(starless, stars_layer, 30)
    full = service.recombine(starless, stars_layer, 100)

    stripped = _star_brightness(starless, stars)
    assert stripped < _star_brightness(faint, stars) < _star_brightness(full, stars)


def test_recombine_screen_blend_only_brightens_and_never_clips(service: StarlessService) -> None:
    starless = np.full((32, 32, 3), 200, dtype=np.uint8)
    stars_layer = np.full((32, 32, 3), 200, dtype=np.uint8)
    out = service.recombine(starless, stars_layer, 100)
    assert out.dtype == np.uint8
    assert int(out.max()) <= 255
    assert (out >= starless).all()
