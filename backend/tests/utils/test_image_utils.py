"""Image IO helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.exceptions import UnsupportedImageError
from app.utils import image_utils


def test_decode_roundtrip(sample_jpeg: bytes) -> None:
    """Encoded JPEG bytes decode back to a same-shape BGR uint8 array."""
    image = image_utils.decode_image(sample_jpeg)
    assert image.ndim == 3
    assert image.shape[2] == 3
    assert image.dtype == np.uint8


def test_decode_rejects_garbage() -> None:
    """Non-image bytes raise UnsupportedImageError."""
    with pytest.raises(UnsupportedImageError):
        image_utils.decode_image(b"not an image")


def test_save_and_load(tmp_path: Path, sample_image: np.ndarray) -> None:
    """A saved image loads back with the same dimensions."""
    path = tmp_path / "out.jpg"
    image_utils.save_image(sample_image, path)
    assert path.exists()
    loaded = image_utils.load_image(path)
    assert loaded.shape == sample_image.shape


def test_make_preview_caps_longest_edge(sample_image: np.ndarray) -> None:
    """Preview downscales so the longest edge is <= max_size, keeping aspect."""
    big = np.zeros((400, 800, 3), dtype=np.uint8)
    preview = image_utils.make_preview(big, max_size=256)
    assert max(preview.shape[:2]) == 256
    assert preview.shape[1] == 2 * preview.shape[0]


def test_make_preview_never_upscales(sample_image: np.ndarray) -> None:
    """A small image is returned unchanged."""
    out = image_utils.make_preview(sample_image, max_size=512)
    assert out.shape == sample_image.shape


def test_compute_histogram_shape(sample_image: np.ndarray) -> None:
    """Histogram has 256 integer bins per channel that sum to the pixel count."""
    hist = image_utils.compute_histogram(sample_image)
    pixels = sample_image.shape[0] * sample_image.shape[1]
    for channel in ("r", "g", "b"):
        assert len(hist[channel]) == 256
        assert sum(hist[channel]) == pixels


def test_encode_image_formats(sample_image: np.ndarray) -> None:
    """JPEG and PNG encoders produce non-empty, distinct byte streams."""
    jpeg = image_utils.encode_image(sample_image, "jpeg", 80)
    png = image_utils.encode_image(sample_image, "png")
    assert jpeg[:2] == b"\xff\xd8"  # JPEG SOI marker
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
