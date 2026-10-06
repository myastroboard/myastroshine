"""LooksService tests - the optional "Style" finishing looks.

Each building block is checked for: identity at strength 0, the direction of
its effect, output validity (float32, same shape, in [0, 1]), and the "no
invented detail" guardrail - a look must not create fine structure where the
input has none.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from app.models import LookParameters, ProcessingParameters
from app.services import looks
from app.services.image_processing import ImageProcessingService
from app.services.looks import LOOKS, LooksService
from app.services.storage import PRELOOK_THUMB_MAX_SIZE

_OPERATIONS = (
    looks.local_contrast,
    looks.orton_glow,
    looks.deep_black,
    looks.colour_pop,
    looks.split_toning,
    looks.vignette,
    looks.warm_tone,
    looks.cool_tone,
    looks.lift_shadows,
    looks.inner_glow,
    looks.star_glow,
    looks.star_colour,
    looks.core_and_arms,
    looks.disc_detail,
    looks.band_detail,
)
_SKY = 0.08


def _astro_scene(height: int = 240, width: int = 360, seed: int = 7, stars: int = 25) -> np.ndarray:
    """A dark noisy sky, a reddish nebula with a filament, and a few stars (BGR float32)."""
    rng = np.random.default_rng(seed)
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    nebula = np.exp(
        -(((xs - width / 2) / (width / 5)) ** 2 + ((ys - height / 2) / (height / 4)) ** 2)
    )
    filament = 0.15 * np.exp(-(((ys - height / 2 - 0.3 * (xs - width / 2)) / 3.0) ** 2)) * nebula
    image = np.full((height, width, 3), _SKY, dtype=np.float32)
    image += (0.45 * nebula + filament)[:, :, np.newaxis] * np.array([0.5, 0.6, 1.0], np.float32)
    for _ in range(stars):
        y, x = rng.integers(5, height - 5), rng.integers(5, width - 5)
        image += (0.8 * np.exp(-((xs - x) ** 2 + (ys - y) ** 2) / 2.0))[:, :, np.newaxis]
    image += rng.normal(0.0, 0.01, image.shape).astype(np.float32)
    return np.clip(image, 0.0, 1.0).astype(np.float32)


def _luma(image: np.ndarray) -> np.ndarray:
    return np.asarray(image @ np.array([0.0722, 0.7152, 0.2126], dtype=np.float32))


def _chroma(image: np.ndarray) -> np.ndarray:
    return np.asarray(image.max(axis=2) - image.min(axis=2))


def _fine_energy(image: np.ndarray) -> float:
    """Standard deviation of the pixel-scale detail (image minus a 1 px blur)."""
    return float(np.std(image - cv2.GaussianBlur(image, (0, 0), 1.0)))


@pytest.fixture
def scene() -> np.ndarray:
    return _astro_scene()


@pytest.mark.parametrize("operation", _OPERATIONS)
def test_operation_is_identity_at_zero(operation: looks.Operation, scene: np.ndarray) -> None:
    """Every building block returns its input untouched at strength 0."""
    assert operation(scene, 0.0) is scene


@pytest.mark.parametrize("operation", _OPERATIONS)
def test_operation_output_is_valid(operation: looks.Operation, scene: np.ndarray) -> None:
    """Full strength keeps the shape, stays float32 and inside [0, 1]."""
    out = operation(scene, 1.0)
    assert out.shape == scene.shape
    assert out.dtype == np.float32
    assert float(out.min()) >= 0.0
    assert float(out.max()) <= 1.0
    assert not np.array_equal(out, scene)


def test_deep_black_darkens_the_sky_and_never_brightens(scene: np.ndarray) -> None:
    """The background goes darker, nothing gets brighter, and white stays white."""
    out = looks.deep_black(scene, 1.0)
    assert float(np.median(_luma(out))) < 0.7 * float(np.median(_luma(scene)))
    assert np.all(out <= scene + 1e-6)
    white = np.ones((8, 8, 3), dtype=np.float32)
    white[:4] = _SKY
    assert np.allclose(looks.deep_black(white, 1.0)[4:], 1.0)


def test_deep_black_on_a_black_frame_is_identity() -> None:
    """With no sky level to work from (an all-black frame), nothing changes."""
    black = np.zeros((8, 8, 3), dtype=np.float32)
    assert looks.deep_black(black, 1.0) is black


def test_deep_black_leaves_a_bright_frame_mostly_alone() -> None:
    """A frame with no dark sky (a daylit Moon close-up) has its sky level capped."""
    bright = np.full((16, 16, 3), 0.9, dtype=np.float32)
    out = looks.deep_black(bright, 1.0)
    assert float(out.mean()) > 0.6


def test_orton_glow_brightens_the_object_but_not_the_sky(scene: np.ndarray) -> None:
    """The glow comes from bright areas; the background sky level barely moves."""
    out = looks.orton_glow(scene, 1.0)
    centre = (slice(110, 130), slice(170, 190))
    assert float(out[centre].mean()) > float(scene[centre].mean()) + 0.02
    corner = (slice(0, 20), slice(0, 20))
    assert abs(float(out[corner].mean()) - float(scene[corner].mean())) < 0.01


def test_local_contrast_does_not_sharpen_pixel_noise() -> None:
    """On pure noise, the band-pass leaves the pixel-scale grain essentially unchanged."""
    rng = np.random.default_rng(3)
    noise = np.clip(0.3 + rng.normal(0.0, 0.02, (200, 300, 3)), 0.0, 1.0).astype(np.float32)
    out = looks.local_contrast(noise, 1.0)
    assert _fine_energy(out) < 1.1 * _fine_energy(noise)


def test_local_contrast_lifts_medium_scale_structure() -> None:
    """Medium-scale structure (the filament) stands out more.

    Measured on a starless scene: stars are shielded on purpose (see the star
    bloat test below), so they must not be counted as "structure" here.
    """
    scene = _astro_scene(stars=0)

    def band(image: np.ndarray) -> float:
        luma = _luma(image)
        return float(
            np.std(cv2.GaussianBlur(luma, (0, 0), 1.5) - cv2.GaussianBlur(luma, (0, 0), 8))
        )

    assert band(looks.local_contrast(scene, 1.0)) > 1.2 * band(scene)


def test_local_contrast_does_not_bloat_stars() -> None:
    """Stars sit in the same band as structure; the boost leaves them their size."""
    height, width = 240, 360
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    image = np.full((height, width, 3), _SKY, dtype=np.float32)
    # A faint star and a bright one with a wide halo (it reaches white in its core).
    for y, x, peak, sigma in ((60, 90, 0.5, 1.2), (150, 250, 3.0, 4.0)):
        star = peak * np.exp(-((xs - x) ** 2 + (ys - y) ** 2) / (2 * sigma * sigma))
        image += star[:, :, np.newaxis]
    image = np.clip(image + np.random.default_rng(2).normal(0, 0.005, image.shape), 0, 1)
    image = image.astype(np.float32)

    out = looks.local_contrast(image, 1.0)

    def area_above(img: np.ndarray, level: float) -> int:
        return int(np.count_nonzero(_luma(img) > level))

    for level in (0.3, 0.6):
        assert area_above(out, level) <= area_above(image, level) * 1.1 + 2


def test_colour_pop_saturates_the_object_not_the_sky(scene: np.ndarray) -> None:
    """Chroma rises on the nebula; the background's colour noise is left alone."""
    out = looks.colour_pop(scene, 1.0)
    centre = (slice(110, 130), slice(170, 190))
    assert float(_chroma(out[centre]).mean()) > 1.15 * float(_chroma(scene[centre]).mean())
    corner = (slice(0, 20), slice(0, 20))
    assert np.allclose(_chroma(out[corner]), _chroma(scene[corner]), atol=0.01)
    unclipped = out.max(axis=2) < 0.999  # only a saturated star core may lose luminance
    assert np.allclose(_luma(out)[unclipped], _luma(scene)[unclipped], atol=0.02)


def test_split_toning_keeps_luminance_and_a_black_sky() -> None:
    """The tints carry no luminance, and pure black stays neutral black.

    The ramp stops below white: a tint pushed past 1 is clipped, as anywhere else.
    """
    ramp = np.repeat(np.linspace(0.0, 0.8, 64, dtype=np.float32)[:, np.newaxis], 8, axis=1)
    grey = np.repeat(ramp[:, :, np.newaxis], 3, axis=2)
    out = looks.split_toning(grey, 1.0)
    assert np.allclose(_luma(out), _luma(grey), atol=0.01)
    assert np.allclose(out[0], 0.0)
    shadows, highlights = out[16], out[60]
    assert float(shadows[:, 0].mean()) > float(shadows[:, 2].mean())  # cool: blue over red
    assert float(highlights[:, 2].mean()) > float(highlights[:, 0].mean())  # warm: red over blue


def test_vignette_darkens_corners_and_keeps_the_centre() -> None:
    """Corners go darker; the centre is untouched."""
    flat = np.full((101, 151, 3), 0.5, dtype=np.float32)
    out = looks.vignette(flat, 1.0)
    assert float(out[0, 0, 0]) < 0.4
    assert float(out[50, 75, 0]) == pytest.approx(0.5)


@pytest.mark.parametrize("look_id", sorted(LOOKS))
def test_looks_invent_no_detail_on_a_flat_frame(look_id: str) -> None:
    """A featureless frame gets no fine structure from any look."""
    flat = np.full((120, 180, 3), 0.25, dtype=np.float32)
    out = LooksService().apply(flat, LookParameters(look_id=look_id, amount=100))
    assert _fine_energy(out) < 1e-3


@pytest.mark.parametrize("look_id", sorted(LOOKS))
def test_looks_do_not_amplify_pixel_noise(look_id: str) -> None:
    """On a pure-noise sky, no look raises the pixel-scale grain."""
    rng = np.random.default_rng(11)
    noise = np.clip(_SKY + rng.normal(0.0, 0.01, (200, 300, 3)), 0.0, 1.0).astype(np.float32)
    out = LooksService().apply(noise, LookParameters(look_id=look_id, amount=100))
    assert _fine_energy(out) < 1.1 * _fine_energy(noise)


@pytest.mark.parametrize("look_id", sorted(LOOKS))
def test_look_on_a_thumbnail_matches_the_full_size_look(look_id: str) -> None:
    """Sizes are relative to the image, so a gallery thumbnail previews the export faithfully.

    The thumbnail is the gallery's real size (``PRELOOK_THUMB_MAX_SIZE``): far
    smaller, stars shrink below a pixel and no star-aware look could match.
    """
    full = _astro_scene(800, 1200)
    size = (PRELOOK_THUMB_MAX_SIZE, round(PRELOOK_THUMB_MAX_SIZE * 800 / 1200))
    small = cv2.resize(full, size, interpolation=cv2.INTER_AREA)
    params = LookParameters(look_id=look_id, amount=100)
    styled_then_shrunk = cv2.resize(
        LooksService().apply(full, params), size, interpolation=cv2.INTER_AREA
    )
    shrunk_then_styled = LooksService().apply(small, params)
    assert float(np.abs(styled_then_shrunk - shrunk_then_styled).mean()) < 0.01


def test_service_without_a_look_is_identity(scene: np.ndarray) -> None:
    """No look, or amount 0, returns the image unchanged."""
    service = LooksService()
    assert service.apply(scene, LookParameters()) is scene
    assert service.apply(scene, LookParameters(look_id="vivid", amount=0)) is scene


def test_amount_scales_the_effect(scene: np.ndarray) -> None:
    """A higher amount moves the image further from the original."""
    service = LooksService()
    gentle = service.apply(scene, LookParameters(look_id="vivid", amount=30))
    strong = service.apply(scene, LookParameters(look_id="vivid", amount=100))
    assert float(np.abs(strong - scene).mean()) > float(np.abs(gentle - scene).mean()) > 0.0


def test_unknown_look_is_rejected() -> None:
    """An id outside the catalogue fails validation instead of being ignored."""
    with pytest.raises(ValidationError):
        LookParameters(look_id="sparkle_spikes")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        LookParameters(look_id="vivid", amount=101)


def test_pipeline_leaves_the_look_to_apply_look() -> None:
    """``apply_parameters`` renders the edit before its look: the look is a final
    layer applied by ``apply_look``, so the pre-look result can be kept."""
    image = (_astro_scene() * 255).astype(np.uint8)
    service = ImageProcessingService()
    steps: list[str] = []
    with_look = ProcessingParameters(contrast=1.2, look=LookParameters(look_id="soft_glow"))
    rendered = service.apply_parameters(image, with_look, lambda name, _pct: steps.append(name))

    assert "look" not in steps
    assert np.array_equal(
        rendered, service.apply_parameters(image, ProcessingParameters(contrast=1.2))
    )


def test_apply_look_on_an_8_bit_image() -> None:
    """``apply_look`` takes and returns uint8; no look is byte-identical."""
    image = (_astro_scene() * 255).astype(np.uint8)
    service = ImageProcessingService()

    styled = service.apply_look(image, LookParameters(look_id="vivid"))

    assert styled.dtype == np.uint8
    assert styled.shape == image.shape
    assert not np.array_equal(styled, image)
    assert np.array_equal(service.apply_look(image, LookParameters()), image)


def _nightscape(height: int = 240, width: int = 320) -> tuple[np.ndarray, np.ndarray]:
    """A noisy sky with a bright diagonal band over a dark, slightly lit foreground.

    Returns the image and its sky mask (1 = sky), the horizon at two thirds down.
    """
    rng = np.random.default_rng(5)
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    horizon = int(height * 2 / 3)
    band = 0.35 * np.exp(-(((xs - ys * 1.2) / (width / 8)) ** 2))
    image = np.full((height, width, 3), 0.12, dtype=np.float32)
    image += (band)[:, :, np.newaxis] * np.array([0.8, 0.9, 1.0], np.float32)
    image[horizon:] = np.array([0.03, 0.05, 0.06], np.float32)  # dark foreground
    image += rng.normal(0.0, 0.005, image.shape).astype(np.float32)
    mask = np.zeros((height, width), dtype=np.float32)
    mask[:horizon] = 1.0
    return np.clip(image, 0.0, 1.0), mask


@pytest.mark.parametrize("look_id", ["galactic_core", "blue_hour"])
def test_night_landscape_look_treats_sky_and_foreground_apart(look_id: str) -> None:
    """The foreground gets only its own steps: lifted, never darkened, no sky toning."""
    image, mask = _nightscape()
    out = LooksService().apply(image, LookParameters(look_id=look_id, amount=100), mask)
    ground = (slice(200, 240), slice(0, 320))
    sky = (slice(0, 120), slice(0, 320))
    assert float(_luma(out[ground]).mean()) > float(_luma(image[ground]).mean())
    assert not np.allclose(out[sky], image[sky], atol=0.01)


def test_galactic_core_keeps_the_foreground_hue() -> None:
    """Galactic core lifts the foreground without tinting it like the sky."""
    image, mask = _nightscape()
    out = LooksService().apply(image, LookParameters(look_id="galactic_core", amount=100), mask)
    ground = out[200:240].reshape(-1, 3).mean(axis=0)
    source = image[200:240].reshape(-1, 3).mean(axis=0)
    assert np.allclose(ground / ground.sum(), source / source.sum(), atol=0.01)


def test_blue_hour_cools_the_sky_and_warms_the_foreground() -> None:
    image, mask = _nightscape()
    out = LooksService().apply(image, LookParameters(look_id="blue_hour", amount=100), mask)
    sky_shift = out[:120].reshape(-1, 3).mean(axis=0) - image[:120].reshape(-1, 3).mean(axis=0)
    ground_shift = out[200:].reshape(-1, 3).mean(axis=0) - image[200:].reshape(-1, 3).mean(axis=0)
    assert sky_shift[0] > sky_shift[2]  # more blue than red in the sky
    assert ground_shift[2] > ground_shift[0]  # more red than blue on the ground


def test_night_landscape_look_draws_no_halo_round_a_badly_masked_tree() -> None:
    """A dark tree the sky matte only half covers gets no bright rim in the sky next to it.

    The phone's matte is coarser than a tree: dark leaves counted as "sky" must
    not pull the local sky level down and make the sky beside them glow.
    """
    height, width = 240, 320
    rng = np.random.default_rng(9)
    image = np.full((height, width, 3), 0.3, dtype=np.float32)
    image += rng.normal(0.0, 0.004, image.shape).astype(np.float32)
    image[60:240, 200:260] = 0.04  # a dark tree trunk and crown
    mask = np.ones((height, width), dtype=np.float32)
    mask[60:240, 215:245] = 0.0  # the matte misses the tree's outer 15 px each side
    out = LooksService().apply(image, LookParameters(look_id="galactic_core", amount=100), mask)

    beside_tree = _luma(out[100:200, 180:198]).mean()
    open_sky = _luma(out[100:200, 20:80]).mean()
    assert beside_tree < open_sky + 0.01


def test_night_landscape_look_without_a_mask_styles_the_whole_frame() -> None:
    """No sky mask (an API call on an ordinary image): the sky steps apply everywhere."""
    image, _ = _nightscape()
    with_none = LooksService().apply(image, LookParameters(look_id="blue_hour", amount=80))
    assert with_none.shape == image.shape
    assert not np.array_equal(with_none, image)


def test_night_landscape_look_resizes_a_smaller_mask() -> None:
    """A mask at another resolution is resized to the image."""
    image, mask = _nightscape()
    small = cv2.resize(mask, (80, 60), interpolation=cv2.INTER_NEAREST)
    full = LooksService().apply(image, LookParameters(look_id="galactic_core"), mask)
    resized = LooksService().apply(image, LookParameters(look_id="galactic_core"), small)
    assert float(np.abs(full - resized).mean()) < 0.01


@pytest.mark.parametrize("operation", [looks.warm_tone, looks.cool_tone, looks.lift_shadows])
def test_tone_and_lift_keep_black_black(operation: looks.Operation) -> None:
    """Warm / cool tones and the shadow lift are gains, never offsets."""
    black = np.zeros((8, 8, 3), dtype=np.float32)
    assert np.array_equal(operation(black, 1.0), black)
    assert operation(black, 0.0) is black


def _star_field(height: int = 240, width: int = 360) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """A dark sky with coloured stars (blue and orange) and their positions."""
    rng = np.random.default_rng(4)
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    image = np.full((height, width, 3), _SKY, dtype=np.float32)
    spots = []
    for index in range(30):
        y, x = int(rng.integers(10, height - 10)), int(rng.integers(10, width - 10))
        # BGR: odd stars blue, even stars orange.
        colour = np.array([1.0, 0.8, 0.5] if index % 2 else [0.5, 0.75, 1.0], np.float32)
        star = 0.7 * np.exp(-((xs - x) ** 2 + (ys - y) ** 2) / 3.0)
        image += star[:, :, np.newaxis] * colour
        spots.append((y, x))
    image += rng.normal(0.0, 0.004, image.shape).astype(np.float32)
    return np.clip(image, 0.0, 1.0).astype(np.float32), spots


def test_star_glow_blooms_round_the_stars_only() -> None:
    """The glow brightens the stars' surroundings, not the empty sky far from any star."""
    image, spots = _star_field()
    out = looks.star_glow(image, 1.0)
    y, x = spots[0]
    ring = (slice(y - 4, y + 5), slice(x - 4, x + 5))
    assert float(out[ring].mean()) > float(image[ring].mean()) + 0.01
    far = np.ones(image.shape[:2], dtype=bool)
    for sy, sx in spots:
        far[max(0, sy - 20) : sy + 20, max(0, sx - 20) : sx + 20] = False
    assert np.allclose(out[far], image[far], atol=0.005)


def test_star_colour_deepens_star_colours_and_spares_the_sky() -> None:
    """Blue stars get bluer, orange ones more orange; the sky keeps its colour."""
    image, spots = _star_field()
    out = looks.star_colour(image, 1.0)
    for index, (y, x) in enumerate(spots[:6]):
        before, after = image[y, x], out[y, x]
        if index % 2:  # blue star: blue over red grows
            assert after[0] - after[2] > before[0] - before[2]
        else:  # orange star: red over blue grows
            assert after[2] - after[0] > before[2] - before[0]
    assert np.allclose(out[:5, :5], image[:5, :5], atol=0.002)


def test_core_and_arms_warms_the_core_and_cools_the_outskirts() -> None:
    """On a galaxy-like disc, the bright core warms and the fainter outskirts cool."""
    height, width = 240, 360
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    disc = np.exp(-(((xs - 180) / 70) ** 2 + ((ys - 120) / 35) ** 2))
    grey = (_SKY + 0.6 * disc).astype(np.float32)
    image = np.repeat(grey[:, :, np.newaxis], 3, axis=2)
    out = looks.core_and_arms(image, 1.0)
    core, arm = out[120, 180], out[120, 245]
    assert core[2] > core[0]  # warm: red over blue
    assert arm[0] > arm[2]  # cool: blue over red
    assert np.allclose(out[:10, :10], image[:10, :10])  # sky untouched
    assert np.allclose(_luma(out), _luma(image), atol=0.01)


def test_inner_glow_lifts_a_frame_filling_nebula_where_orton_glow_barely_does() -> None:
    """When the nebula is the median level, only the low-percentile floor finds a glow."""
    height, width = 240, 360
    rng = np.random.default_rng(6)
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    clouds = 0.3 + 0.15 * np.sin(xs / 25.0) * np.cos(ys / 30.0)
    image = np.repeat(clouds[:, :, np.newaxis], 3, axis=2).astype(np.float32)
    image *= np.array([0.6, 0.6, 1.0], np.float32)
    image += rng.normal(0.0, 0.003, image.shape).astype(np.float32)
    inner = float(np.abs(looks.inner_glow(image, 1.0) - image).mean())
    plain = float(np.abs(looks.orton_glow(image, 1.0) - image).mean())
    assert inner > 1.5 * plain


def test_inner_glow_does_not_swell_a_bright_star() -> None:
    """The nebula glow is made without the stars: a bright star keeps its size."""
    height, width = 240, 360
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    star = 2.0 * np.exp(-((xs - 180) ** 2 + (ys - 120) ** 2) / (2 * 3.0**2))
    image = np.clip(_SKY + star, 0.0, 1.0)[:, :, np.newaxis].repeat(3, axis=2).astype(np.float32)
    out = looks.inner_glow(image, 1.0)
    halo = (slice(105, 135), slice(165, 195))
    assert float(np.abs(out[halo] - image[halo]).max()) < 0.05


def test_local_contrast_does_not_burn_a_bright_core() -> None:
    """A bright core keeps its detail: lifts fade out towards white."""
    height, width = 240, 360
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    core = 0.85 * np.exp(-(((xs - 180) / 60) ** 2 + ((ys - 120) / 60) ** 2))
    ripples = 0.06 * np.sin(xs / 6.0) * np.exp(-(((xs - 180) / 60) ** 2))
    grey = np.clip(_SKY + core + ripples, 0.0, 1.0).astype(np.float32)
    image = np.repeat(grey[:, :, np.newaxis], 3, axis=2)
    out = looks.local_contrast(image, 1.0)
    assert int(np.count_nonzero(out >= 0.999)) <= int(np.count_nonzero(image >= 0.999)) + 20


def _planet(
    size: int = 400, diameter: float = 120.0, seed: int = 8
) -> tuple[np.ndarray, np.ndarray]:
    """A banded, slightly coloured disc on black (a Jupiter-like planet) and its mask."""
    rng = np.random.default_rng(seed)
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32)
    centre = size / 2
    radius = diameter / 2
    inside = (xs - centre) ** 2 + (ys - centre) ** 2 <= radius**2
    bands = 0.55 + 0.08 * np.sin((ys - centre) / radius * 9.0)
    image = np.zeros((size, size, 3), dtype=np.float32)
    image[inside] = (bands[inside])[:, np.newaxis] * np.array([0.8, 0.9, 1.0], np.float32)
    image += rng.normal(0.0, 0.004, image.shape).astype(np.float32)
    return np.clip(image, 0.0, 1.0).astype(np.float32), inside


def test_band_detail_sharpens_the_bands_and_leaves_the_sky_black() -> None:
    """Bands gain contrast inside the disc; the black sky and the limb get no ring."""
    image, inside = _planet()
    out = looks.band_detail(image, 1.0)
    core = (slice(170, 230), slice(170, 230))
    assert float(_luma(out[core]).std()) > 1.15 * float(_luma(image[core]).std())
    ring = np.zeros_like(inside)
    ys, xs = np.mgrid[0:400, 0:400]
    distance = np.sqrt((xs - 200) ** 2 + (ys - 200) ** 2)
    ring[(distance > 62) & (distance < 75)] = True  # just outside the limb
    assert float(np.abs(out[ring] - image[ring]).max()) < 0.01


def test_disc_detail_scales_with_the_disc_not_the_frame() -> None:
    """A small planet in a big black field gets the same treatment as a tight crop of it."""
    image, _ = _planet(size=800, diameter=120.0)
    crop = image[300:500, 300:500].copy()
    wide = looks.band_detail(image, 1.0)[300:500, 300:500]
    tight = looks.band_detail(crop, 1.0)
    assert float(np.abs(wide - tight).mean()) < 0.003


def test_disc_detail_ignores_a_frame_without_a_disc() -> None:
    """No disc bigger than a few pixels (a star field): nothing to sharpen."""
    image = np.zeros((100, 100, 3), dtype=np.float32)
    image[50, 50] = 1.0
    assert looks.disc_detail(image, 1.0) is image


def test_disc_detail_does_not_amplify_noise_on_a_flat_disc() -> None:
    """A featureless disc keeps its grain."""
    size = 300
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32)
    inside = (xs - 150) ** 2 + (ys - 150) ** 2 <= 90**2
    rng = np.random.default_rng(1)
    image = np.zeros((size, size, 3), dtype=np.float32)
    image[inside] = 0.5
    image += rng.normal(0.0, 0.01, image.shape).astype(np.float32) * inside[:, :, np.newaxis]
    image = np.clip(image, 0.0, 1.0)
    out = looks.disc_detail(image, 1.0)
    centre = (slice(110, 190), slice(110, 190))
    assert _fine_energy(out[centre]) < 1.1 * _fine_energy(image[centre])


def test_rich_colour_brings_out_a_planet_colour() -> None:
    """Rich colour deepens the disc's own colour and leaves the sky black."""
    image, inside = _planet()
    out = LooksService().apply(image, LookParameters(look_id="rich_colour", amount=100))
    assert float(_chroma(out)[inside].mean()) > 1.2 * float(_chroma(image)[inside].mean())
    assert float(out[:20, :20].max()) < 0.03


def _moon(size: int = 600, diameter: float = 400.0) -> np.ndarray:
    """A grey disc with small craters (bright rims, dark floors) on black."""
    rng = np.random.default_rng(12)
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32)
    centre, radius = size / 2, diameter / 2
    inside = (xs - centre) ** 2 + (ys - centre) ** 2 <= radius**2
    grey = np.where(inside, 0.5, 0.0).astype(np.float32)
    for _ in range(40):
        angle, r = rng.uniform(0, 2 * np.pi), rng.uniform(0, radius * 0.85)
        cy, cx = centre + r * np.sin(angle), centre + r * np.cos(angle)
        d2 = (xs - cx) ** 2 + (ys - cy) ** 2
        grey += np.where(inside, 0.08 * np.exp(-d2 / 30.0) - 0.08 * np.exp(-d2 / 8.0), 0.0)
    grey += rng.normal(0.0, 0.004, grey.shape).astype(np.float32) * inside
    return np.repeat(np.clip(grey, 0.0, 1.0)[:, :, np.newaxis], 3, axis=2).astype(np.float32)


def test_disc_detail_sharpens_lunar_craters() -> None:
    """Crater-scale detail gains contrast; the sky round the Moon stays black."""
    image = _moon()
    out = looks.disc_detail(image, 1.0)

    def crater_contrast(img: np.ndarray) -> float:
        luma = _luma(img[200:400, 200:400])
        band = cv2.GaussianBlur(luma, (0, 0), 1.0) - cv2.GaussianBlur(luma, (0, 0), 6.0)
        return float(np.std(band))

    assert crater_contrast(out) > 1.1 * crater_contrast(image)
    assert float(out[:40, :40].max()) < 0.02
