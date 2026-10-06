"""Sky masks: reading Apple's ProRAW sky matte, and fitting a mask to an image."""

from __future__ import annotations

import struct

import cv2
import numpy as np

from app.utils.sky_mask import fit_sky_mask, read_apple_sky_matte

_SKY_NAME = b"urn:com:apple:photo:2020:aux:semanticskymatte\x00"


def _matte(height: int = 60, width: int = 80) -> np.ndarray:
    """Sky (255) above a dark band of landscape along the bottom quarter."""
    matte = np.full((height, width), 255, dtype=np.uint8)
    matte[height * 3 // 4 :] = 0
    return matte


def _tiff_with_matte(
    matte: np.ndarray, orientation: int = 1, name: bytes = _SKY_NAME, order: str = "<"
) -> bytes:
    """A minimal TIFF (little-endian by default): IFD0 (Orientation, SubIFDs) -> one sub-IFD
    holding the matte as a JPEG strip, tagged with its semantic name - the layout
    of an Apple ProRAW's auxiliary images."""
    ok, jpeg = cv2.imencode(".jpg", matte)
    assert ok
    strip = jpeg.tobytes()
    ifd0_at = 8
    ifd0_size = 2 + 2 * 12 + 4
    sub_at = ifd0_at + ifd0_size
    sub_size = 2 + 3 * 12 + 4
    name_at = sub_at + sub_size
    strip_at = name_at + len(name)

    def entry(tag: int, kind: int, count: int, value: bytes) -> bytes:
        return struct.pack(order + "HHI", tag, kind, count) + value.ljust(4, b"\x00")

    ifd0 = (
        struct.pack(order + "H", 2)
        + entry(274, 3, 1, struct.pack(order + "H", orientation))
        + entry(330, 4, 1, struct.pack(order + "I", sub_at))
        + struct.pack(order + "I", 0)
    )
    sub = (
        struct.pack(order + "H", 3)
        + entry(273, 4, 1, struct.pack(order + "I", strip_at))
        + entry(279, 4, 1, struct.pack(order + "I", len(strip)))
        + entry(52526, 2, len(name), struct.pack(order + "I", name_at))
        + struct.pack(order + "I", 0)
    )
    magic = b"II*\x00" if order == "<" else b"MM\x00*"
    return magic + struct.pack(order + "I", ifd0_at) + ifd0 + sub + name + strip


def test_reads_the_sky_matte_from_a_proraw_layout() -> None:
    """The sky matte sub-IFD is found and its JPEG strip decoded."""
    matte = read_apple_sky_matte(_tiff_with_matte(_matte()))
    assert matte is not None
    assert matte.shape == (60, 80)
    assert matte[:30].mean() > 240  # sky
    assert matte[-5:].mean() < 15  # landscape


def test_reads_a_big_endian_tiff() -> None:
    """Motorola byte order (``MM``) is read as well as Intel (``II``)."""
    matte = read_apple_sky_matte(_tiff_with_matte(_matte(), order=">"))
    assert matte is not None
    assert matte.shape == (60, 80)


def test_the_matte_follows_the_image_orientation() -> None:
    """Orientation 6 (rotate 90 deg clockwise) turns the landscape-format matte
    portrait, the way libraw renders the image itself."""
    matte = read_apple_sky_matte(_tiff_with_matte(_matte(), orientation=6))
    assert matte is not None
    assert matte.shape == (80, 60)
    assert matte[:, :5].mean() < 15  # the bottom band is now on the left


def test_a_file_without_a_sky_matte_has_no_mask() -> None:
    """Another auxiliary image, a non-TIFF file, or a truncated one: no mask."""
    assert read_apple_sky_matte(_tiff_with_matte(_matte(), name=b"depth\x00")) is None
    assert read_apple_sky_matte(b"SIMPLE  = T" + b"\x00" * 64) is None
    assert read_apple_sky_matte(_tiff_with_matte(_matte())[:20]) is None
    assert read_apple_sky_matte(_tiff_with_matte(_matte())[:-10]) is None  # strip cut short


def test_a_corrupt_directory_is_ignored() -> None:
    """An implausible IFD entry count is treated as corruption, not looped over."""
    corrupt = b"II*\x00" + struct.pack("<I", 8) + struct.pack("<H", 0xFFFF) + b"\x00" * 32
    assert read_apple_sky_matte(corrupt) is None


def test_fit_sky_mask_resizes_to_the_image() -> None:
    """A matte at a quarter resolution becomes a full-size boolean mask."""
    sky = fit_sky_mask(_matte(), (240, 320, 3))
    assert sky is not None
    assert sky.shape == (240, 320)
    assert sky.dtype == bool
    assert sky[:100].all()
    assert not sky[-20:].any()


def test_fit_sky_mask_ignores_an_all_sky_or_mismatched_mask() -> None:
    """An all-sky mask means "no landscape" (the deep-sky path), and a mask whose
    aspect ratio does not match belongs to another image: both give ``None``."""
    assert fit_sky_mask(np.full((60, 80), 255, np.uint8), (240, 320)) is None
    assert fit_sky_mask(_matte(), (320, 240)) is None
    assert fit_sky_mask(None, (240, 320)) is None


def test_fit_sky_mask_ignores_a_mask_with_almost_no_sky() -> None:
    """A matte that marks (almost) nothing as sky - an indoor shot, a matte that
    missed the sky - gives no mask, instead of empty sky statistics downstream."""
    assert fit_sky_mask(np.zeros((60, 80), np.uint8), (240, 320)) is None
    nearly_none = np.zeros((60, 80), np.uint8)
    nearly_none[:2] = 255  # ~3% sky
    assert fit_sky_mask(nearly_none, (240, 320)) is None


def test_a_matte_without_strip_tags_is_ignored() -> None:
    """A matte sub-IFD without StripOffsets / StripByteCounts (a tiled layout)
    gives no mask rather than an error."""
    data = bytearray(_tiff_with_matte(_matte()))
    sub_ifd_entries = 8 + (2 + 2 * 12 + 4) + 2  # header + IFD0, then the sub-IFD's entry count
    assert struct.unpack_from("<H", data, sub_ifd_entries)[0] == 273  # its first entry
    struct.pack_into("<H", data, sub_ifd_entries, 322)  # StripOffsets -> TileWidth
    assert read_apple_sky_matte(bytes(data)) is None
