"""Linear deconvolution: the PSF measured off the stars, Richardson-Lucy, its safeguards."""

from __future__ import annotations

import numpy as np
import pytest

from app.services.deconvolution import deconvolve, estimate_psf_sigma, richardson_lucy

SKY = 0.05
NOISE = 0.002
PSF_SIGMA = 2.0


def _field(
    *, stars: int = 60, sigma: float = PSF_SIGMA, seed: int = 1, size: int = 256
) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """A linear RGB composite: a flat sky, white noise, and Gaussian stars of a
    known PSF - the first one a bright orange star, the rest white."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    image = np.full((size, size, 3), SKY, dtype=np.float32)
    centres: list[tuple[int, int]] = []
    for index in range(stars):
        x, y = int(rng.integers(12, size - 12)), int(rng.integers(12, size - 12))
        peak = 0.6 if index == 0 else float(rng.uniform(0.08, 0.4))
        colour = np.array([1.0, 0.6, 0.3]) if index == 0 else np.ones(3)
        blob = peak * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sigma**2))
        image += blob[:, :, np.newaxis] * colour.astype(np.float32)
        centres.append((x, y))
    image += rng.normal(0.0, NOISE, image.shape).astype(np.float32)
    return image, centres


def _luma(image: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(image @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32))


def test_estimates_the_psf_of_the_stars() -> None:
    image, _ = _field()
    sigma = estimate_psf_sigma(_luma(image))
    assert sigma == pytest.approx(PSF_SIGMA, rel=0.15)


def test_no_psf_without_enough_stars() -> None:
    image, _ = _field(stars=3)
    assert estimate_psf_sigma(_luma(image)) is None


def test_richardson_lucy_conserves_flux_and_tightens_a_star() -> None:
    plane = np.zeros((64, 64), dtype=np.float32) + 0.01
    yy, xx = np.mgrid[0:64, 0:64].astype(np.float32)
    plane += np.exp(-((xx - 32) ** 2 + (yy - 32) ** 2) / (2 * PSF_SIGMA**2)).astype(np.float32)
    out = richardson_lucy(plane, PSF_SIGMA, 15)
    assert float(out.sum()) == pytest.approx(float(plane.sum()), rel=0.01)
    assert float(out[32, 32]) > 1.5 * float(plane[32, 32])


def test_amount_zero_is_the_identity() -> None:
    image, _ = _field()
    assert deconvolve(image, 0) is image


def test_too_few_stars_leaves_the_composite_untouched() -> None:
    image, _ = _field(stars=3)
    assert deconvolve(image, 80) is image


def test_deconvolution_sharpens_stars_but_not_the_sky_noise() -> None:
    """Stars get tighter (higher peaks); the background - nothing but noise - keeps
    its level and its noise; the total flux is kept."""
    image, centres = _field()
    out = deconvolve(image, 80)

    peaks_before = np.mean([image[y, x].sum() for x, y in centres])
    peaks_after = np.mean([out[y, x].sum() for x, y in centres])
    assert peaks_after > 1.2 * peaks_before

    corner_before, corner_after = image[:10, :10], out[:10, :10]
    assert float(corner_after.mean()) == pytest.approx(float(corner_before.mean()), abs=NOISE)
    assert float(corner_after.std()) == pytest.approx(float(corner_before.std()), rel=0.1)
    assert float(out.sum()) == pytest.approx(float(image.sum()), rel=0.02)


def test_deconvolution_keeps_star_colour_and_digs_no_dark_ring() -> None:
    image, centres = _field()
    out = deconvolve(image, 100)
    x, y = centres[0]  # the bright orange star

    # A star's colour is its photometry: the light above the sky in an aperture
    # (what the colour calibration measures). Each channel is deconvolved on its
    # own, so its flux is redistributed, never moved to another channel.
    yy, xx = np.mgrid[0 : image.shape[0], 0 : image.shape[1]]
    aperture = np.hypot(xx - x, yy - y) <= 3 * PSF_SIGMA
    before = (image[aperture] - SKY).sum(axis=0)
    after = (out[aperture] - SKY).sum(axis=0)
    assert after[1] / after[0] == pytest.approx(before[1] / before[0], rel=0.02)
    assert after[2] / after[0] == pytest.approx(before[2] / before[0], rel=0.02)

    ring = (np.hypot(xx - x, yy - y) > 2.5 * PSF_SIGMA) & (np.hypot(xx - x, yy - y) < 5 * PSF_SIGMA)
    assert float(out[ring].min()) > SKY - 5 * NOISE


def test_deconvolves_a_mono_composite() -> None:
    image, centres = _field()
    mono = np.ascontiguousarray(image[..., 1])
    out = deconvolve(mono, 80)
    assert out.shape == mono.shape
    assert np.mean([out[y, x] for x, y in centres]) > np.mean([mono[y, x] for x, y in centres])
