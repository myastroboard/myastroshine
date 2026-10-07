"""Star-referenced colour calibration of a linear composite."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.services.color_calibration import LUMA_RGB, neutralise_sky, star_white_balance


def _star_field(
    cast: tuple[float, float, float],
    *,
    stars: int = 150,
    size: int = 600,
    nebula: tuple[float, float, float] | None = None,
    seed: int = 0,
) -> np.ndarray:
    """A linear RGB frame of white Gaussian stars, seen through a sensor ``cast``.

    ``nebula`` adds a large, strongly coloured diffuse blob - the kind of target
    that fools a "balance the channel means" calibration.
    """
    rng = np.random.default_rng(seed)
    white = np.zeros((size, size), dtype=np.float32)
    for _ in range(stars):
        x, y = rng.integers(20, size - 20, 2)
        white[y, x] = rng.uniform(0.05, 0.4)
    white = cv2.GaussianBlur(white, (0, 0), 1.6) * 20.0
    rgb = np.repeat(white[:, :, np.newaxis], 3, axis=2)
    if nebula is not None:
        blob = np.zeros((size, size), dtype=np.float32)
        cv2.circle(blob, (size // 2, size // 2), size // 3, 1.0, -1)
        blob = cv2.GaussianBlur(blob, (0, 0), size / 10)
        rgb += blob[:, :, np.newaxis] * np.array(nebula, dtype=np.float32) * 0.05
    rgb *= np.array(cast, dtype=np.float32)
    rgb += 0.02 + rng.normal(0, 0.0005, rgb.shape).astype(np.float32)
    return rgb


def _star_colour(rgb: np.ndarray) -> np.ndarray:
    """Median colour (normalised to G) of the brightest pixels - the star cores."""
    luma = rgb @ LUMA_RGB
    cores = rgb[luma > np.percentile(luma, 99.7)]
    return np.median(cores / cores[:, 1:2], axis=0)


def test_neutralise_sky_centres_each_channel_on_zero_without_clipping() -> None:
    """The sky of every channel lands on zero and the noise keeps its negative
    half - clipping it would leave a noise-proportional colour bias."""
    frame = _star_field((1.0, 1.0, 1.0)) + np.array([0.3, 0.1, 0.05], dtype=np.float32)

    neutral, sky = neutralise_sky(frame)

    assert sky == pytest.approx([0.32, 0.12, 0.07], abs=0.002)
    assert np.abs(np.median(neutral, axis=(0, 1))).max() < 1e-3
    assert float(neutral.min()) < 0.0


def test_neutralise_sky_leaves_no_green_cast_on_a_noisy_sky() -> None:
    """Equal noise in every channel leaves every channel's sky at the same level.

    Picking "the darker half" pixel by pixel on luminance (72% green) picks the
    pixels whose green noise is low, so green's sky level came out lowest and a
    green residual was left on the sky - the green background of every stretched
    composite.
    """
    rng = np.random.default_rng(11)
    sigma = 0.01
    frame = (0.05 + rng.normal(0.0, sigma, (600, 600, 3))).astype(np.float32)

    neutral, _ = neutralise_sky(frame)

    residual = np.median(neutral, axis=(0, 1))
    assert float(residual.max() - residual.min()) < 0.05 * sigma


def test_star_white_balance_removes_a_sensor_cast() -> None:
    """A Seestar-like cast (weak blue) is measured on the stars and undone."""
    frame, _ = neutralise_sky(_star_field((1.4, 1.0, 0.3)))

    gains = star_white_balance(frame)

    assert gains is not None
    assert _star_colour(frame * gains) == pytest.approx([1.0, 1.0, 1.0], abs=0.05)


def test_star_white_balance_keeps_luminance() -> None:
    """The gains are normalised so the overall brightness is unchanged."""
    frame, _ = neutralise_sky(_star_field((1.2, 1.0, 0.6)))
    gains = star_white_balance(frame)
    assert gains is not None
    assert float(gains @ LUMA_RGB) == pytest.approx(1.0, abs=1e-5)


def test_star_white_balance_is_not_fooled_by_a_coloured_nebula() -> None:
    """A big red nebula stays red: the reference is the stars, not the frame mean."""
    frame, _ = neutralise_sky(_star_field((1.0, 1.0, 1.0), nebula=(1.0, 0.1, 0.1)))

    gains = star_white_balance(frame)

    assert gains is not None
    assert gains == pytest.approx([1.0, 1.0, 1.0], abs=0.08)


def test_star_white_balance_gives_up_on_too_few_stars() -> None:
    """Under the minimum star count the median is not trusted - ``None``."""
    frame, _ = neutralise_sky(_star_field((1.3, 1.0, 0.5), stars=5))
    assert star_white_balance(frame) is None


def test_star_white_balance_skips_saturated_stars() -> None:
    """Clipped stars carry no colour information; with only those, it gives up."""
    frame, _ = neutralise_sky(_star_field((1.3, 1.0, 0.5)))
    frame = np.where(frame > 0.02, 1.0, frame).astype(np.float32)  # every star clipped flat
    assert star_white_balance(frame) is None


def test_star_white_balance_handles_an_empty_frame() -> None:
    """A frame with no detection at all returns ``None`` instead of failing."""
    flat = np.zeros((200, 200, 3), dtype=np.float32)
    assert star_white_balance(flat) is None


def test_star_white_balance_measures_a_large_frame_on_a_downscaled_copy() -> None:
    """A frame bigger than the photometry size is measured on a downscale and
    still recovers the cast."""
    frame, _ = neutralise_sky(_star_field((1.3, 1.0, 0.5), size=2400, stars=600, seed=3))
    gains = star_white_balance(frame)
    assert gains is not None
    assert _star_colour(frame * gains) == pytest.approx([1.0, 1.0, 1.0], abs=0.06)


def test_neutralise_sky_measures_the_sky_inside_the_mask() -> None:
    """With a sky mask, a dark landscape is not mistaken for the sky level."""
    rng = np.random.default_rng(5)
    linear = (np.array([0.02, 0.015, 0.01]) + rng.normal(0, 0.0005, (90, 120, 3))).astype(
        np.float32
    )
    linear[60:] = 0.001  # landscape: the darker third of the frame
    sky = np.zeros((90, 120), dtype=bool)
    sky[:60] = True

    _, level = neutralise_sky(linear, sky)
    assert np.allclose(level, [0.02, 0.015, 0.01], atol=0.001)
    _, unmasked_level = neutralise_sky(linear)
    assert unmasked_level[0] < 0.005  # without it, the landscape is the "sky"
