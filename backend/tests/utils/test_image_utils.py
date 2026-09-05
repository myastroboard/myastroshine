"""Image IO helpers."""

from __future__ import annotations

import io
from pathlib import Path

import cv2
import numpy as np
import pytest
import rawpy

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


def test_decode_grayscale_png_becomes_3_channel_bgr(sample_image: np.ndarray) -> None:
    """A single-channel source (cv2.IMREAD_UNCHANGED) still comes back as 3-channel BGR."""
    gray = cv2.cvtColor(sample_image, cv2.COLOR_BGR2GRAY)
    ok, buffer = cv2.imencode(".png", gray)
    assert ok
    image = image_utils.decode_image(buffer.tobytes(), "gray.png")
    assert image.shape == (*gray.shape, 3)
    assert image.dtype == np.uint8


def test_decode_rgba_png_drops_alpha(sample_image: np.ndarray) -> None:
    """A 4-channel source is flattened to plain BGR, matching the old IMREAD_COLOR behaviour."""
    rgba = cv2.cvtColor(sample_image, cv2.COLOR_BGR2BGRA)
    ok, buffer = cv2.imencode(".png", rgba)
    assert ok
    image = image_utils.decode_image(buffer.tobytes(), "rgba.png")
    assert image.shape == sample_image.shape
    assert image.dtype == np.uint8


def test_decode_16bit_png_is_auto_stretched() -> None:
    """A 16-bit source (e.g. a stacked TIFF/PNG) is auto-stretched, not truncated."""
    rng = np.random.default_rng(3)
    data = np.clip(rng.normal(3000, 200, size=(30, 40, 3)), 0, 65535).astype(np.uint16)
    ok, buffer = cv2.imencode(".png", data)
    assert ok
    image = image_utils.decode_image(buffer.tobytes(), "stack.png")
    assert image.dtype == np.uint8
    assert image.shape == (30, 40, 3)
    # background should land near the stretch's ~0.25 target, not stay crushed near 0
    assert 30 < int(np.median(image)) < 100


def _fits_bytes(data: np.ndarray) -> bytes:
    from astropy.io import fits

    buffer = io.BytesIO()
    fits.PrimaryHDU(data=data).writeto(buffer)
    return buffer.getvalue()


def test_decode_fits_mono_auto_stretches() -> None:
    """A 2D FITS plane (the common single-sensor case) becomes gray-replicated BGR."""
    rng = np.random.default_rng(1)
    data = rng.normal(500, 20, size=(40, 60)).astype(np.float32)
    data[10, 10] = 40000  # a bright "star" pixel

    image = image_utils.decode_image(_fits_bytes(data), "frame.fits")

    assert image.shape == (40, 60, 3)
    assert image.dtype == np.uint8
    assert np.array_equal(image[:, :, 0], image[:, :, 1])
    assert np.array_equal(image[:, :, 1], image[:, :, 2])
    assert 40 < int(np.median(image)) < 90


def test_decode_fits_tolerates_nan_blank_pixels() -> None:
    """NaN/blank pixels (registered-stack edges, dead pixels) don't blank the frame."""
    rng = np.random.default_rng(7)
    data = rng.normal(500, 20, size=(40, 60)).astype(np.float32)
    data[10, 10] = 40000
    data[0:3, 0:3] = np.nan  # a blank corner

    image = image_utils.decode_image(_fits_bytes(data), "frame.fits")

    assert image.dtype == np.uint8
    assert int(image[:, :, 0].max()) > 0  # not an all-black plane
    assert int(image[20:, 20:, 0].mean()) > 10  # real signal survived the stretch


def test_decode_fits_rgb_planes_map_to_correct_bgr_channels() -> None:
    """A (3, H, W) FITS cube is read as R/G/B planes and reordered to BGR."""
    background = np.full((12, 12), 500.0, dtype=np.float32)
    red, green, blue = background.copy(), background.copy(), background.copy()
    red[2, 2] = 50000
    green[6, 6] = 50000
    blue[9, 9] = 50000
    cube = np.stack([red, green, blue])

    image = image_utils.decode_image(_fits_bytes(cube), "frame.fits")

    assert image.shape == (12, 12, 3)
    assert image[2, 2, 2] > 200  # red plane's bright spot -> BGR channel 2 (R)
    assert image[2, 2, 0] < 100
    assert image[2, 2, 1] < 100
    assert image[6, 6, 1] > 200  # green plane's bright spot -> BGR channel 1 (G)
    assert image[9, 9, 0] > 200  # blue plane's bright spot -> BGR channel 0 (B)


def test_decode_fits_rejects_garbage() -> None:
    """Non-FITS bytes with a .fits extension raise UnsupportedImageError, not a crash."""
    with pytest.raises(UnsupportedImageError):
        image_utils.decode_image(b"not a fits file", "broken.fits")


def test_decode_fits_rejects_a_header_declared_oversized_shape() -> None:
    """A FITS header can claim a huge NAXIS1/NAXIS2 with no real data behind it
    (a 2880-byte header alone can declare 50000x50000) - decode_image must reject
    this from the header alone, before ever allocating an array that size."""
    from astropy.io import fits

    header = fits.Header(
        [
            ("SIMPLE", True),
            ("BITPIX", -32),
            ("NAXIS", 2),
            ("NAXIS1", 50000),
            ("NAXIS2", 50000),
            ("EXTEND", True),
        ]
    )
    crafted = header.tostring(padding=True).encode("ascii")

    with pytest.raises(UnsupportedImageError, match="exceeding"):
        image_utils.decode_image(crafted, "huge.fits")


def test_decode_fits_rejects_an_oversized_declared_shape_of_any_ndim() -> None:
    """The header-only size guard must catch every declared shape, not just the
    2D/3-plane-cube ones this module actually accepts - a shape this module would
    otherwise reject as "unsupported" must still be caught before allocating."""
    from astropy.io import fits

    header = fits.Header(
        [
            ("SIMPLE", True),
            ("BITPIX", -32),
            ("NAXIS", 4),
            ("NAXIS1", 5000),
            ("NAXIS2", 5000),
            ("NAXIS3", 5),
            ("NAXIS4", 5),
            ("EXTEND", True),
        ]
    )
    crafted = header.tostring(padding=True).encode("ascii")

    with pytest.raises(UnsupportedImageError, match="exceeding"):
        image_utils.decode_image(crafted, "huge_cube.fits")


def test_decode_fits_rejects_unsupported_shape() -> None:
    """A FITS data cube that isn't 2D or a 3-plane RGB cube is rejected clearly."""
    data = np.zeros((2, 4, 5), dtype=np.float32)
    with pytest.raises(UnsupportedImageError, match="shape"):
        image_utils.decode_image(_fits_bytes(data), "cube.fits")


def test_decode_raw_dispatches_by_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    """A recognised RAW extension routes through rawpy, then normalizes to BGR uint8."""

    class _FakeRaw:
        def __enter__(self) -> _FakeRaw:
            return self

        def __exit__(self, *exc_info: object) -> None:
            return None

        def postprocess(self, **kwargs: object) -> np.ndarray:
            return np.full((4, 6, 3), 128, dtype=np.uint8)

    monkeypatch.setattr(rawpy, "imread", lambda _file: _FakeRaw())

    image = image_utils.decode_image(b"fake raw bytes", "photo.CR2")

    assert image.shape == (4, 6, 3)
    assert image.dtype == np.uint8


def test_decode_raw_rejects_garbage() -> None:
    """Non-RAW bytes with a RAW extension raise UnsupportedImageError, not a libraw crash."""
    with pytest.raises(UnsupportedImageError):
        image_utils.decode_image(b"not a raw file", "photo.nef")


def test_decode_rejects_images_over_the_pixel_cap(
    sample_jpeg: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A decoded image over MAX_IMAGE_PIXELS is rejected - guards against a
    small (compressed) upload decompressing into a huge array. Uses the small
    sample fixture against a lowered cap rather than building a real huge
    image, which would be slow and memory-heavy for no extra coverage."""
    monkeypatch.setattr(image_utils, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(UnsupportedImageError, match="exceeding"):
        image_utils.decode_image(sample_jpeg)


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
