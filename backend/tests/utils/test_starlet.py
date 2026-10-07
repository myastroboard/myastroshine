"""Starlet wavelet transform, denoise and detail enhancement."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.utils.starlet import (
    denoise_plane,
    enhance_detail,
    layer_noise,
    noise_sigma,
    starlet_transform,
)


def _field(noise: float = 0.02, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """``(clean, noisy)``: a smooth ramp plus Gaussian stars, and that with noise."""
    rng = np.random.default_rng(seed)
    _, xx = np.mgrid[0:256, 0:256].astype(np.float32)
    clean = 0.2 + 0.1 * xx / 256
    stars = np.zeros_like(clean)
    for x, y in rng.integers(10, 246, (25, 2)):
        stars[y, x] = 1.0
    clean += cv2.GaussianBlur(stars, (0, 0), 1.2) * 5.0
    noisy = clean + rng.normal(0, noise, clean.shape).astype(np.float32)
    return clean.astype(np.float32), noisy.astype(np.float32)


def test_transform_reconstructs_exactly() -> None:
    _, noisy = _field()
    details, residual = starlet_transform(noisy, 5)
    assert len(details) == 5
    assert np.allclose(residual + sum(details), noisy, atol=1e-5)


def test_noise_sigma_reads_white_noise_level() -> None:
    noise = np.random.default_rng(1).normal(0, 0.05, (300, 300)).astype(np.float32)
    assert noise_sigma(noise) == pytest.approx(0.05, rel=0.1)


def test_denoise_lowers_the_error_to_the_clean_image() -> None:
    clean, noisy = _field()
    out = denoise_plane(noisy, 3.0, 4)
    assert float(np.abs(out - clean).mean()) < 0.6 * float(np.abs(noisy - clean).mean())


def test_denoise_keeps_star_peaks() -> None:
    """Large coefficients pass the garrote nearly intact - stars are not dimmed
    the way a blur or a bilateral filter dims them."""
    clean, noisy = _field()
    out = denoise_plane(noisy, 3.0, 4)
    peak = np.unravel_index(np.argmax(clean), clean.shape)
    assert out[peak] == pytest.approx(noisy[peak], rel=0.1)


def test_denoise_zero_threshold_is_identity() -> None:
    _, noisy = _field()
    assert denoise_plane(noisy, 0.0, 4) is noisy


def test_denoise_of_a_noiseless_plane_is_identity() -> None:
    flat = np.full((64, 64), 0.3, dtype=np.float32)
    assert denoise_plane(flat, 2.0, 3) is flat


def _correlated_grain(sigma: float = 0.05, seed: int = 3) -> np.ndarray:
    """Noise correlated over a pixel or two, as debayering and the registration of
    stacked frames leave it - it drains the finest layer most."""
    white = np.random.default_rng(seed).normal(0, sigma, (300, 300)).astype(np.float32)
    return cv2.GaussianBlur(white, (0, 0), 0.8)


def test_layer_noise_reads_correlated_noise_above_the_white_model() -> None:
    """The coarser layers' noise follows the second layer, not an extrapolation
    from the drained finest layer."""
    details, _ = starlet_transform(_correlated_grain(), 4)
    white_model = noise_sigma(_correlated_grain()) * 0.086

    noise = layer_noise(details)

    assert noise[2] > 1.5 * white_model


def test_layer_noise_matches_the_white_model_on_white_noise() -> None:
    white = np.random.default_rng(2).normal(0, 0.05, (300, 300)).astype(np.float32)
    details, _ = starlet_transform(white, 4)

    noise = layer_noise(details)

    assert noise[2] == pytest.approx(0.05 * 0.086, rel=0.15)


def test_denoise_removes_correlated_grain() -> None:
    """Correlated grain goes too - with thresholds extrapolated from the finest
    layer, half of it survived on the coarser layers."""
    grain = _correlated_grain()
    flat = np.full(grain.shape, 0.3, dtype=np.float32)

    out = denoise_plane(flat + grain, 3.0, 4)

    assert float((out - flat).std()) < 0.25 * float(grain.std())


def test_a_bright_star_does_not_raise_the_threshold_around_itself() -> None:
    """A faint star beside a bright one keeps most of its peak: the local noise map
    caps each coefficient, so the bright star is not read as local noise (it
    raised the threshold round itself up to 4x and ate its faint neighbours)."""
    rng = np.random.default_rng(3)
    clean = np.full((300, 300), 0.2, dtype=np.float32)
    peaks = np.zeros_like(clean)
    faint = []
    for i in range(12):
        for j in range(12):
            y, x = 12 + i * 23, 12 + j * 23
            peaks[y, x] = 30.0
            peaks[y + 5, x + 5] = 1.2
            faint.append((y + 5, x + 5))
    clean += cv2.GaussianBlur(peaks, (0, 0), 1.2)
    noisy = clean + rng.normal(0, 0.01, clean.shape).astype(np.float32)

    out = denoise_plane(noisy, 3.0, 4)

    kept = [(out[p] - 0.2) / (clean[p] - 0.2) for p in faint]
    assert float(np.median(kept)) > 0.6


def test_global_threshold_mode_also_denoises() -> None:
    clean, noisy = _field()
    out = denoise_plane(noisy, 3.0, 4, local=False)
    assert float(np.abs(out - clean).mean()) < float(np.abs(noisy - clean).mean())


def test_enhance_detail_sharpens_stars_but_not_the_noise() -> None:
    clean, noisy = _field()
    out = enhance_detail(noisy, 1.0, 2)
    peak = np.unravel_index(np.argmax(clean), clean.shape)
    assert out[peak] > noisy[peak] * 1.1
    grain = np.random.default_rng(9).normal(0.3, 0.02, (256, 256)).astype(np.float32)
    assert float(enhance_detail(grain, 1.0, 2).std()) < float(grain.std()) * 1.1


def test_enhance_detail_zero_is_identity() -> None:
    _, noisy = _field()
    assert enhance_detail(noisy, 0.0, 2) is noisy
