"""AutoAstroService: what it measures and what it proposes for each kind of picture."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.models import ProcessingParameters
from app.services.auto_astro import AutoAstroService
from app.services.image_processing import ImageProcessingService
from app.services.star_detection import StarDetectionService


@pytest.fixture
def service() -> AutoAstroService:
    return AutoAstroService(StarDetectionService())


def _frame(
    *,
    sky: tuple[float, float, float] = (28.0, 28.0, 28.0),
    noise: float = 4.0,
    object_colour: tuple[float, float, float] = (40.0, 50.0, 90.0),
    stars: int = 120,
    size: tuple[int, int] = (300, 400),
    seed: int = 0,
) -> np.ndarray:
    """A stretched deep-sky picture: a sky (BGR levels) with independent noise in
    each channel, a soft coloured object filling the middle, and point stars."""
    rng = np.random.default_rng(seed)
    height, width = size
    image = np.zeros((height, width, 3), dtype=np.float32)
    image[:] = sky
    blob = np.zeros((height, width), dtype=np.float32)
    cv2.ellipse(blob, (width // 2, height // 2), (width // 5, height // 6), 30, 0, 360, 1.0, -1)
    blob = cv2.GaussianBlur(blob, (0, 0), min(height, width) / 15)
    image += blob[:, :, np.newaxis] * np.array(object_colour, dtype=np.float32)
    points = np.zeros((height, width), dtype=np.float32)
    for _ in range(stars):
        y, x = int(rng.integers(5, height - 5)), int(rng.integers(5, width - 5))
        points[y, x] = float(rng.uniform(150.0, 900.0))
    image += cv2.GaussianBlur(points, (0, 0), 1.0)[:, :, np.newaxis]
    image += rng.normal(0.0, noise, image.shape).astype(np.float32)
    return np.clip(image, 0, 255).astype(np.uint8)


def _background_bgr(image: np.ndarray) -> np.ndarray:
    """Median level of each channel over the frame's darker, star-free corners."""
    corners = np.concatenate(
        [image[:40, :60].reshape(-1, 3), image[-40:, -60:].reshape(-1, 3)], axis=0
    )
    return np.median(corners, axis=0)


def _render(image: np.ndarray, params: ProcessingParameters) -> np.ndarray:
    return ImageProcessingService().apply_parameters(image, params)


def test_never_moves_the_tone_sliders(service: AutoAstroService) -> None:
    """The tone sliders are left alone: driving them (shadows -0.35 plus a negative
    exposure) is what crushed real stacks' skies to black."""
    params = service.suggest_parameters(_frame())

    assert params.contrast == 1.0
    assert params.exposure == 0.0
    assert params.highlights == 0.0
    assert params.shadows == 0.0
    assert params.blacks == 0.0


def test_deepens_the_sky_without_clipping_it(service: AutoAstroService) -> None:
    """The sky comes out darker, and still well clear of black - its faint signal
    (a galaxy's halo) lives just above it."""
    image = _frame()
    params = service.suggest_parameters(image)
    result = _render(image, params)

    before = float(_background_bgr(image).mean())
    after = float(_background_bgr(result).mean())
    gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
    assert 10.0 < after < before
    assert float((gray <= 2).mean()) < 0.005


def test_tone_curve_keeps_black_and_lifts_a_faint_object(service: AutoAstroService) -> None:
    """The curve pins black at black and moves the object up toward the midtones."""
    image = _frame(object_colour=(30.0, 35.0, 60.0))
    measured = service.measure(image)

    params = service.suggest_parameters(image)

    points = [(p.x, p.y) for p in params.curve_points]
    assert points[0] == (0, 0)
    assert points[-1] == (255, 255)
    object_point = next(p for p in points if p[0] == round(measured.object_level))
    assert object_point[1] > object_point[0]


def test_a_faint_object_is_lifted_at_most_three_times_as_steeply(
    service: AutoAstroService,
) -> None:
    """A faint object asks for a steep curve; it is capped, since the same slope
    posterises 8-bit data and multiplies the noise just above the sky."""
    params = service.suggest_parameters(_frame(object_colour=(25.0, 30.0, 45.0), noise=2.0))

    sky, obj = params.curve_points[1], params.curve_points[2]
    assert (obj.y - sky.y) / (obj.x - sky.x) <= 3.0


def test_denoise_accounts_for_the_curve_gain(service: AutoAstroService) -> None:
    """The denoise runs after the curve: the same noise under a steeper curve is
    more visible, so it gets a stronger denoise."""
    faint = service.suggest_parameters(_frame(object_colour=(25.0, 30.0, 45.0), noise=2.0))
    bright = service.suggest_parameters(_frame(object_colour=(80.0, 90.0, 150.0), noise=2.0))

    assert faint.denoise > bright.denoise


def test_neutralises_a_sky_cast(service: AutoAstroService) -> None:
    """An additive skyglow cast (a yellow sky: weak blue) is undone with
    per-channel curves - the sky comes out grey."""
    image = _frame(sky=(22.0, 32.0, 33.0))

    params = service.suggest_parameters(image)
    result = _render(image, params)

    assert params.blue_curve_points
    background = _background_bgr(result)
    assert float(background.max() - background.min()) <= 3.0


def test_a_neutral_sky_gets_no_channel_curves(service: AutoAstroService) -> None:
    params = service.suggest_parameters(_frame())

    assert params.curve_points
    assert not params.red_curve_points
    assert not params.green_curve_points
    assert not params.blue_curve_points


def test_denoise_follows_the_noise(service: AutoAstroService) -> None:
    """A noisy frame gets luma and colour denoise, capped; a clean one gets none."""
    noisy = service.suggest_parameters(_frame(noise=6.0))
    clean = service.suggest_parameters(_frame(noise=0.0))

    assert 0 < noisy.denoise <= 40
    assert 0 < noisy.chroma_denoise <= 60
    assert clean.denoise == 0
    assert clean.chroma_denoise == 0


def test_a_star_field_gets_a_capped_star_reduction(service: AutoAstroService) -> None:
    params = service.suggest_parameters(_frame(stars=400))

    assert 0 < params.star_reduction <= 30


def test_a_pale_object_gets_more_vibrance_than_a_vivid_one(service: AutoAstroService) -> None:
    """A galaxy's pale colour is boosted; an already vivid nebula much less."""
    pale = service.suggest_parameters(_frame(object_colour=(60.0, 62.0, 66.0)))
    vivid = service.suggest_parameters(_frame(object_colour=(10.0, 20.0, 160.0)))

    assert pale.vibrance > vivid.vibrance >= 1.15


def test_a_green_object_gets_green_removal(service: AutoAstroService) -> None:
    """A green cast on the object (a one-shot-colour sensor's extra green) is removed."""
    params = service.suggest_parameters(_frame(object_colour=(40.0, 90.0, 40.0)))

    assert params.green_removal > 0


def test_a_blue_nebula_keeps_its_colour(service: AutoAstroService) -> None:
    params = service.suggest_parameters(_frame(object_colour=(90.0, 50.0, 30.0)))

    assert params.green_removal == 0


def test_a_night_landscape_keeps_its_stars_and_calm_colour(service: AutoAstroService) -> None:
    """With a sky mask: no star reduction (the stars are the subject), no colour
    boost, and the camera's coarse colour mottle is smoothed."""
    image = _frame(stars=400)
    image[220:] = 3  # the dark landscape
    sky = np.zeros(image.shape[:2], dtype=np.uint8)
    sky[:220] = 255

    params = service.suggest_parameters(image, sky)

    assert params.star_reduction == 0
    assert params.vibrance == 1.0
    assert params.chroma_denoise >= 50


def test_the_sky_mask_keeps_the_landscape_out_of_the_sky_level(
    service: AutoAstroService,
) -> None:
    """Without the mask, the black landscape would be taken for the sky."""
    image = _frame()
    image[150:] = 2
    sky = np.zeros((75, 100), dtype=np.uint8)  # a quarter-resolution matte
    sky[:37] = 255

    masked = service.measure(image, cv2.resize(sky, (400, 300)) > 0)
    unmasked = service.measure(image)

    assert masked.sky > 20.0
    assert unmasked.sky < 5.0


def test_a_wide_field_frame_is_treated_as_a_landscape(service: AutoAstroService) -> None:
    params = service.suggest_parameters(_frame(stars=400), wide_field=True)

    assert params.star_reduction == 0
    assert params.vibrance == 1.0


def test_the_moon_on_black_is_only_sharpened(service: AutoAstroService) -> None:
    """A bright disc on a black, noise-free sky: its craters are not stars to
    shrink, and there is no sky to deepen."""
    image = np.zeros((300, 400, 3), dtype=np.uint8)
    cv2.circle(image, (200, 150), 110, (150, 155, 160), -1)
    rng = np.random.default_rng(4)
    for _ in range(300):
        y, x = int(rng.integers(60, 240)), int(rng.integers(110, 290))
        cv2.circle(image, (x, y), int(rng.integers(1, 4)), (90, 95, 100), -1)

    params = service.suggest_parameters(image)

    assert params.star_reduction == 0
    assert not params.curve_points
    assert params.green_removal == 0
    assert params.sharpness > 1.0


def test_a_flat_frame_stays_near_default(service: AutoAstroService) -> None:
    """Nothing to separate and no noise: no curve, no denoise."""
    params = service.suggest_parameters(np.full((120, 160, 3), 128, dtype=np.uint8))

    assert not params.curve_points
    assert params.denoise == 0
    assert params.chroma_denoise == 0
    assert params.star_reduction == 0


def test_a_grayscale_picture_is_analysed(service: AutoAstroService) -> None:
    gray = cv2.cvtColor(_frame(), cv2.COLOR_BGR2GRAY)

    params = service.suggest_parameters(gray)

    assert params.curve_points
    assert not params.blue_curve_points


def test_never_suggests_gradient_reduction(service: AutoAstroService) -> None:
    """A single frame cannot tell a light-pollution gradient from an asymmetric
    bright subject (confirmed against real lunar photos - see
    docs/ALGORITHMS.md); ``gradient_reduction`` stays manual."""
    height, width = 200, 200
    _y, x = np.mgrid[0:height, 0:width]
    ramp = (80 + 60 * (x / width)).astype(np.uint8)
    image = np.stack([ramp, ramp, ramp], axis=-1)

    params = service.suggest_parameters(image)

    assert params.gradient_reduction == 0
