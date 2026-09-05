"""ImageProcessingService algorithm tests.

Each algorithm is checked for: identity at its default value, correct direction
of effect, and output validity (BGR uint8, same shape, in range).
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.models import CurvePoint, GeometryParameters, ProcessingParameters
from app.services.image_processing import ImageProcessingService
from app.utils.math_utils import curve_points_to_lut


@pytest.fixture
def service() -> ImageProcessingService:
    return ImageProcessingService()


def _mean_luma(image: np.ndarray) -> float:
    return float(image.mean())


def test_apply_parameters_identity_with_defaults(
    service: ImageProcessingService, sample_image: np.ndarray
) -> None:
    """All-default parameters return the image byte-for-byte unchanged."""
    out = service.apply_parameters(sample_image, ProcessingParameters())
    assert np.array_equal(out, sample_image)


def test_contrast_identity_at_one(
    service: ImageProcessingService, sample_image: np.ndarray
) -> None:
    """contrast=1.0 is a no-op."""
    assert np.array_equal(service.apply_contrast(sample_image, 1.0), sample_image)


def test_contrast_increases_spread(
    service: ImageProcessingService, sample_image: np.ndarray
) -> None:
    """contrast > 1 widens the tonal distribution."""
    out = service.apply_contrast(sample_image, 2.0)
    assert out.shape == sample_image.shape
    assert out.dtype == np.uint8
    assert out.std() > sample_image.std()


def test_brightness_direction(service: ImageProcessingService, sample_image: np.ndarray) -> None:
    """Positive brightness lifts the mean, negative drops it."""
    assert _mean_luma(service.apply_brightness(sample_image, 0.5)) > _mean_luma(sample_image)
    assert _mean_luma(service.apply_brightness(sample_image, -0.5)) < _mean_luma(sample_image)


def test_saturation_zero_is_greyscale(
    service: ImageProcessingService, sample_image: np.ndarray
) -> None:
    """saturation=0 collapses the colour channels to near-equal values."""
    out = service.apply_saturation(sample_image, 0.0)
    channel_spread = out.max(axis=2).astype(int) - out.min(axis=2).astype(int)
    assert channel_spread.mean() < 5


def test_denoise_off_is_identity(service: ImageProcessingService, sample_image: np.ndarray) -> None:
    """denoise=0 returns the input untouched."""
    assert np.array_equal(service.apply_denoise(sample_image, 0), sample_image)


def test_denoise_reduces_noise_variance(
    service: ImageProcessingService, sample_image: np.ndarray
) -> None:
    """A strong denoise lowers local variance."""
    out = service.apply_denoise(sample_image, 80)
    assert out.shape == sample_image.shape
    assert float(np.var(out)) <= float(np.var(sample_image))


def test_sharpness_identity_at_one(
    service: ImageProcessingService, sample_image: np.ndarray
) -> None:
    """sharpness=1.0 is a no-op."""
    assert np.array_equal(service.apply_sharpness(sample_image, 1.0), sample_image)


def test_star_reduction_off_is_identity(
    service: ImageProcessingService, sample_image: np.ndarray
) -> None:
    """star_reduction=0 returns the input untouched."""
    assert np.array_equal(service.apply_star_reduction(sample_image, 0), sample_image)


def test_star_reduction_dims_stars_more_than_the_object(
    service: ImageProcessingService,
) -> None:
    """Star points lose brightness while a diffuse disc is left alone."""
    image = np.zeros((200, 200, 3), dtype=np.uint8)
    cv2.circle(image, (100, 100), 45, (120, 120, 130), -1)
    image = cv2.GaussianBlur(image, (0, 0), sigmaX=12).astype(np.uint8)
    object_before = int(image[100, 100].astype(int).sum())

    stars = [(20, 20), (180, 20), (20, 180), (180, 180), (100, 25)]
    for x, y in stars:
        cv2.circle(image, (x, y), 3, (255, 255, 255), -1)
    stars_before = float(np.mean([image[y, x].astype(int).sum() for x, y in stars]))

    out = service.apply_star_reduction(image, 80)

    stars_after = float(np.mean([out[y, x].astype(int).sum() for x, y in stars]))
    object_after = int(out[100, 100].astype(int).sum())
    assert out.shape == image.shape
    assert out.dtype == np.uint8
    assert stars_after < stars_before * 0.7
    assert object_after >= object_before * 0.9


def test_star_reduction_sensitivity_gates_faint_points(
    service: ImageProcessingService,
) -> None:
    """A strict threshold shrinks only the obvious star; a loose one catches the faint one too."""
    image = np.zeros((200, 200, 3), dtype=np.uint8)
    cv2.circle(image, (100, 100), 3, (255, 255, 255), -1)  # obvious star
    cv2.circle(image, (30, 30), 2, (70, 70, 70), -1)  # faint star
    before = image.astype(int)

    def _changed(out: np.ndarray, cy: int, cx: int) -> bool:
        window = slice(cy - 4, cy + 5), slice(cx - 4, cx + 5)
        return bool(np.abs(out.astype(int)[window] - before[window]).sum() > 0)

    strict = service.apply_star_reduction(image, 80, sensitivity=0, max_size=30)
    loose = service.apply_star_reduction(image, 80, sensitivity=95, max_size=30)

    assert _changed(strict, 100, 100)  # the obvious star is always shrunk
    assert not _changed(strict, 30, 30)  # too faint for a strict threshold
    assert _changed(loose, 30, 30)  # a looser threshold catches it too


def test_star_reduction_leaves_untouched_pixels_far_from_any_star(
    service: ImageProcessingService,
) -> None:
    """Only the star's own footprint is blended; the rest of the frame is exact."""
    image = np.zeros((200, 200, 3), dtype=np.uint8)
    image[:, :] = (40, 40, 45)  # a flat, dim "sky" background
    cv2.circle(image, (100, 100), 3, (255, 255, 255), -1)

    out = service.apply_star_reduction(image, 80, sensitivity=70, max_size=30)

    corner = out[5:15, 5:15]
    assert np.array_equal(corner, image[5:15, 5:15])


def test_star_reduction_fades_into_background_not_black(
    service: ImageProcessingService,
) -> None:
    """Regression: a fully-shrunk star must fade to its local background, not black.

    An earlier version blended toward a darkened, eroded copy; for a small
    isolated star, erosion's local-minimum fill crushed straight to near-zero
    regardless of the actual surrounding colour, showing up as a visible black
    dot at full strength. The fix (`cv2.inpaint`) fills from the real
    neighbouring pixels, so the result must land near the background colour.
    """
    image = np.zeros((200, 200, 3), dtype=np.uint8)
    image[:, :] = (90, 90, 100)  # a lit, mid-tone "sky" - not near-black itself
    cv2.circle(image, (100, 100), 3, (255, 255, 255), -1)

    out = service.apply_star_reduction(image, 100, sensitivity=70, max_size=30)

    center = out[100, 100].astype(int)
    background = np.array([90, 90, 100])
    assert np.abs(center - background).max() < 30, f"star center faded to {center}, not background"


def test_geometry_default_is_identity(
    service: ImageProcessingService, sample_image: np.ndarray
) -> None:
    """All-default geometry returns the image unchanged."""
    assert np.array_equal(service.apply_geometry(sample_image, GeometryParameters()), sample_image)


def test_geometry_quarter_turn_swaps_dimensions(
    service: ImageProcessingService, sample_image: np.ndarray
) -> None:
    """A single 90-degree turn transposes height and width."""
    out = service.apply_geometry(sample_image, GeometryParameters(rotate_quarters=1))
    height, width = sample_image.shape[:2]
    assert out.shape[:2] == (width, height)


def test_geometry_crop_reduces_size_to_the_rectangle(
    service: ImageProcessingService, sample_image: np.ndarray
) -> None:
    """The crop rectangle is honoured in fractions of the image."""
    height, width = sample_image.shape[:2]
    out = service.apply_geometry(
        sample_image, GeometryParameters(crop_x=0.25, crop_y=0.25, crop_w=0.5, crop_h=0.5)
    )
    assert out.shape[:2] == (round(0.5 * height), round(0.5 * width))


def test_geometry_flip_horizontal_mirrors_columns(
    service: ImageProcessingService, sample_image: np.ndarray
) -> None:
    """flip_horizontal reverses the column order."""
    out = service.apply_geometry(sample_image, GeometryParameters(flip_horizontal=True))
    assert np.array_equal(out, sample_image[:, ::-1])


def test_geometry_straighten_keeps_frame_full(
    service: ImageProcessingService, sample_image: np.ndarray
) -> None:
    """Straighten rotates but scales up so no border pixels appear (same shape)."""
    out = service.apply_geometry(sample_image, GeometryParameters(straighten=8.0))
    assert out.shape == sample_image.shape
    assert out.dtype == np.uint8


def test_white_balance_neutral_is_identity(
    service: ImageProcessingService, sample_image: np.ndarray
) -> None:
    """6500K / tint 0 leaves the image unchanged."""
    assert np.array_equal(service.apply_white_balance(sample_image, 6500, 0), sample_image)


def test_white_balance_warm_shifts_towards_red(
    service: ImageProcessingService, sample_image: np.ndarray
) -> None:
    """A low colour temperature reduces the blue channel relative to red."""
    warm = service.apply_white_balance(sample_image, 3000, 0)
    assert warm[:, :, 0].mean() < sample_image[:, :, 0].mean()  # blue drops


def test_tone_curve_empty_is_identity(
    service: ImageProcessingService, sample_image: np.ndarray
) -> None:
    """No control points -> no-op, matching ``curve_points``'s empty default."""
    assert np.array_equal(service.apply_tone_curve(sample_image, []), sample_image)


def test_tone_curve_applies_the_same_lut_as_math_utils(
    service: ImageProcessingService, sample_image: np.ndarray
) -> None:
    """The service wires straight into ``curve_points_to_lut`` via ``cv2.LUT``."""
    points = [CurvePoint(x=0, y=0), CurvePoint(x=128, y=90), CurvePoint(x=255, y=255)]
    out = service.apply_tone_curve(sample_image, points)

    expected = cv2.LUT(sample_image, curve_points_to_lut([(0, 0), (128, 90), (255, 255)]))
    assert np.array_equal(out, expected)


def test_tone_curve_darkens_midtones(
    service: ImageProcessingService, sample_image: np.ndarray
) -> None:
    """A curve pulled below the diagonal at the midpoint darkens the image overall."""
    points = [CurvePoint(x=0, y=0), CurvePoint(x=128, y=80), CurvePoint(x=255, y=255)]
    out = service.apply_tone_curve(sample_image, points)
    assert _mean_luma(out) < _mean_luma(sample_image)


def test_full_pipeline_stays_in_range(
    service: ImageProcessingService, sample_image: np.ndarray
) -> None:
    """A heavy parameter set still yields a valid BGR uint8 image."""
    params = ProcessingParameters(
        geometry=GeometryParameters(straighten=4.0, crop_x=0.1, crop_w=0.8),
        contrast=1.8,
        brightness=0.2,
        saturation=1.5,
        highlights=-0.3,
        shadows=0.4,
        clarity=0.6,
        vibrance=1.3,
        denoise=40,
        star_reduction=50,
        sharpness=1.5,
        temperature=4200,
        tint=10,
        curve_points=[CurvePoint(x=0, y=0), CurvePoint(x=128, y=140), CurvePoint(x=255, y=255)],
    )
    out = service.apply_parameters(sample_image, params)
    height, width = sample_image.shape[:2]
    assert out.shape[0] == height
    assert abs(out.shape[1] - round(0.8 * width)) <= 1  # geometry crop applied first
    assert out.dtype == np.uint8
    assert out.min() >= 0
    assert out.max() <= 255
