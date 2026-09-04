"""CosmicRayService: detecting single-frame outliers."""

from __future__ import annotations

import numpy as np
import pytest

from app.services.cosmic_ray import CosmicRayService


@pytest.fixture
def clean_frames() -> list[np.ndarray]:
    rng = np.random.default_rng(3)
    base = np.full((60, 60, 3), 40, dtype=np.int16)
    return [
        np.clip(base + rng.integers(-4, 5, base.shape), 0, 255).astype(np.uint8) for _ in range(6)
    ]


def test_build_mask_flags_the_injected_ray(clean_frames: list[np.ndarray]) -> None:
    """A bright single-pixel spike in one frame is flagged there and nowhere else."""
    frames = [f.copy() for f in clean_frames]
    frames[2][30, 30] = 255  # cosmic ray in frame 2 only

    mask = CosmicRayService().build_mask(frames, threshold=3.0)

    assert mask[2, 30, 30].all()
    assert not mask[0, 30, 30].any()
    # the clean background is overwhelmingly not flagged
    assert mask.mean() < 0.02


def test_reject_statistical_removes_the_ray(clean_frames: list[np.ndarray]) -> None:
    frames = [f.copy() for f in clean_frames]
    frames[4][10, 10] = 255

    _mask, combined = CosmicRayService().reject_statistical(frames, threshold=3.0)

    assert combined.dtype == np.uint8
    assert int(combined[10, 10].max()) < 80  # ray did not leak into the composite


def test_too_few_frames_returns_empty_mask() -> None:
    frames = [np.zeros((10, 10, 3), np.uint8), np.zeros((10, 10, 3), np.uint8)]
    mask = CosmicRayService().build_mask(frames)
    assert not mask.any()


def test_detect_laplacian_shape(clean_frames: list[np.ndarray]) -> None:
    mask = CosmicRayService().detect_laplacian(clean_frames)
    assert mask.shape == (60, 60, 3)
    assert mask.dtype == bool
