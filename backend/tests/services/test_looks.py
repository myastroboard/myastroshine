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

_OPERATIONS = (
    looks.local_contrast,
    looks.orton_glow,
    looks.deep_black,
    looks.colour_pop,
    looks.split_toning,
    looks.vignette,
)
_SKY = 0.08


def _astro_scene(height: int = 240, width: int = 360, seed: int = 7) -> np.ndarray:
    """A dark noisy sky, a reddish nebula with a filament, and a few stars (BGR float32)."""
    rng = np.random.default_rng(seed)
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    nebula = np.exp(
        -(((xs - width / 2) / (width / 5)) ** 2 + ((ys - height / 2) / (height / 4)) ** 2)
    )
    filament = 0.15 * np.exp(-(((ys - height / 2 - 0.3 * (xs - width / 2)) / 3.0) ** 2)) * nebula
    image = np.full((height, width, 3), _SKY, dtype=np.float32)
    image += (0.45 * nebula + filament)[:, :, np.newaxis] * np.array([0.5, 0.6, 1.0], np.float32)
    for _ in range(25):
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


def test_local_contrast_lifts_medium_scale_structure(scene: np.ndarray) -> None:
    """Medium-scale structure (the filament) stands out more."""

    def band(image: np.ndarray) -> float:
        luma = _luma(image)
        return float(
            np.std(cv2.GaussianBlur(luma, (0, 0), 1.5) - cv2.GaussianBlur(luma, (0, 0), 8))
        )

    assert band(looks.local_contrast(scene, 1.0)) > 1.2 * band(scene)


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
    """Sizes are relative to the image, so a gallery thumbnail previews the export faithfully."""
    full = _astro_scene(480, 720)
    small = cv2.resize(full, (180, 120), interpolation=cv2.INTER_AREA)
    params = LookParameters(look_id=look_id, amount=100)
    styled_then_shrunk = cv2.resize(
        LooksService().apply(full, params), (180, 120), interpolation=cv2.INTER_AREA
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
