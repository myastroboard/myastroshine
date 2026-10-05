"""Sky / foreground masks for nightscape frames.

A Milky Way shot usually has a landscape in the frame (trees, buildings, a
horizon), and every sky statistic the linear pre-stage takes - the background
surface, the sky level, the star colours, the stretch's sky and noise - goes
wrong when those dark, unrelated pixels are counted as sky. A mask that says
which pixels are sky lets those steps measure the sky alone.

Apple ProRAW DNGs carry one for free: a ``semanticskymatte`` auxiliary image
(8-bit, quarter resolution, stored as a JPEG in a sub-IFD). It is read here with
a minimal TIFF directory walk - just enough to find that sub-IFD - so no TIFF
library is needed for it.

A mask, wherever it comes from, is a 2D array with "sky" as high values; use
:func:`fit_sky_mask` to get a boolean mask at a given resolution.
"""

from __future__ import annotations

import struct

import cv2
import numpy as np

from app.logging_config import get_logger

logger = get_logger(__name__)

_TAG_ORIENTATION = 274
_TAG_STRIP_OFFSETS = 273
_TAG_STRIP_BYTE_COUNTS = 279
_TAG_SUB_IFDS = 330
_TAG_SEMANTIC_NAME = 52526
_SKY_MATTE_NAME = b"semanticskymatte"

#: TIFF field type -> byte size of one value.
_TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8, 13: 4}
_SHORT, _LONG, _IFD = 3, 4, 13
_MAX_IFD_ENTRIES = 512  # a real IFD has a few dozen - bounds a corrupt file
_MAX_SUB_IFDS = 16

#: Below this fraction of non-sky pixels a frame is treated as all sky.
_MIN_FOREGROUND_FRACTION = 0.01
_SKY_THRESHOLD = 0.5


def read_apple_sky_matte(data: bytes) -> np.ndarray | None:
    """The ProRAW sky matte, ``uint8`` (255 = sky), in the image's display orientation.

    Returns ``None`` for anything that is not a TIFF-based file carrying one
    (another camera's RAW, a FITS, a ProRAW from before the matte existed) or a
    matte that cannot be decoded - the caller then simply has no mask.
    """
    try:
        return _read_sky_matte(data)
    except struct.error, ValueError, IndexError, cv2.error:
        logger.warning("sky matte unreadable, ignoring it", size=len(data))
        return None


def fit_sky_mask(mask: np.ndarray | None, shape: tuple[int, ...]) -> np.ndarray | None:
    """``mask`` resized to ``shape[:2]`` as a boolean sky mask, or ``None``.

    ``None`` when there is no mask, when its aspect ratio does not match the image
    (it belongs to something else - never stretch a mask onto the wrong frame), or
    when it marks (almost) nothing as foreground: an all-sky frame needs no mask,
    and treating it as maskless keeps the deep-sky code path unchanged.
    """
    if mask is None or mask.ndim != 2:  # noqa: PLR2004 - a 2D mask
        return None
    height, width = shape[:2]
    if abs(mask.shape[1] / mask.shape[0] - width / height) > 0.02:  # noqa: PLR2004
        logger.warning(
            "sky mask aspect mismatch, ignoring it", mask=list(mask.shape), image=[height, width]
        )
        return None
    scale = 255.0 if mask.dtype == np.uint8 else 1.0
    resized = cv2.resize(
        mask.astype(np.float32) / scale, (width, height), interpolation=cv2.INTER_LINEAR
    )
    sky = resized >= _SKY_THRESHOLD
    if 1.0 - float(sky.mean()) < _MIN_FOREGROUND_FRACTION:
        return None
    return sky


def _read_sky_matte(data: bytes) -> np.ndarray | None:
    if data[:4] == b"II*\x00":
        order = "<"
    elif data[:4] == b"MM\x00*":
        order = ">"
    else:
        return None
    ifd0 = _read_ifd(data, order, struct.unpack_from(order + "I", data, 4)[0])
    orientation = int(ifd0.get(_TAG_ORIENTATION, [1])[0])
    for offset in ifd0.get(_TAG_SUB_IFDS, [])[:_MAX_SUB_IFDS]:
        sub = _read_ifd(data, order, int(offset))
        name = sub.get(_TAG_SEMANTIC_NAME)
        if not isinstance(name, bytes) or _SKY_MATTE_NAME not in name:
            continue
        start = int(sub[_TAG_STRIP_OFFSETS][0])
        length = int(sub[_TAG_STRIP_BYTE_COUNTS][0])
        if start + length > len(data):
            return None
        matte = cv2.imdecode(np.frombuffer(data, np.uint8, length, start), cv2.IMREAD_GRAYSCALE)
        return None if matte is None else _orient(matte, orientation)
    return None


def _read_ifd(data: bytes, order: str, offset: int) -> dict[int, list[int] | bytes]:
    """One IFD's entries: integer tags as a list of values, ASCII/byte tags as bytes."""
    (count,) = struct.unpack_from(order + "H", data, offset)
    if count > _MAX_IFD_ENTRIES:
        raise ValueError("implausible IFD entry count")
    entries: dict[int, list[int] | bytes] = {}
    for index in range(count):
        tag, kind, n, raw = struct.unpack_from(order + "HHI4s", data, offset + 2 + index * 12)
        size = _TYPE_SIZES.get(kind, 0) * n
        payload = raw[:size] if size <= 4 else data[_u32(order, raw) : _u32(order, raw) + size]  # noqa: PLR2004
        if kind in (1, 2, 7):  # BYTE / ASCII / UNDEFINED
            entries[tag] = bytes(payload)
        elif kind == _SHORT:
            entries[tag] = list(struct.unpack_from(f"{order}{n}H", payload))
        elif kind in (_LONG, _IFD):
            entries[tag] = list(struct.unpack_from(f"{order}{n}I", payload))
    return entries


def _u32(order: str, raw: bytes) -> int:
    value: int = struct.unpack(order + "I", raw)[0]
    return value


def _orient(image: np.ndarray, orientation: int) -> np.ndarray:
    """Apply the TIFF/EXIF ``Orientation`` rotation (phones never use the mirrored ones)."""
    rotations = {3: cv2.ROTATE_180, 6: cv2.ROTATE_90_CLOCKWISE, 8: cv2.ROTATE_90_COUNTERCLOCKWISE}
    code = rotations.get(orientation)
    return image if code is None else cv2.rotate(image, code)
