"""Starlet wavelet transform, denoise and detail enhancement."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.utils.starlet import denoise_plane, enhance_detail, noise_sigma, starlet_transform


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
