"""Image load / save / inspect helpers.

Thin wrappers over OpenCV so services never touch the library for IO concerns.
All arrays are BGR ``uint8`` (OpenCV's convention) unless stated otherwise.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.exceptions import UnsupportedImageError
from app.logging_config import get_logger

logger = get_logger(__name__)

SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".tiff", ".tif"}

_ENCODE_EXT = {"jpeg": ".jpg", "jpg": ".jpg", "png": ".png", "tiff": ".tif", "tif": ".tif"}


def decode_image(data: bytes) -> np.ndarray:
    """Decode raw image bytes into a BGR ``uint8`` array.

    Raises :class:`UnsupportedImageError` if the bytes are not a readable image.
    """
    buffer = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise UnsupportedImageError("Could not decode image data")
    return image


def load_image(path: Path) -> np.ndarray:
    """Load an image file as a BGR ``uint8`` array."""
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise UnsupportedImageError(f"Could not read image at {path}")
    return image


def save_image(image: np.ndarray, path: Path, quality: int = 95) -> None:
    """Write a BGR array to disk, inferring the format from ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    params: list[int] = []
    suffix = path.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        params = [cv2.IMWRITE_JPEG_QUALITY, int(quality)]
    elif suffix == ".png":
        params = [cv2.IMWRITE_PNG_COMPRESSION, 6]
    if not cv2.imwrite(str(path), image, params):
        raise OSError(f"Failed to write image to {path}")


def encode_image(image: np.ndarray, fmt: str = "jpeg", quality: int = 95) -> bytes:
    """Encode a BGR array to bytes in ``fmt`` (jpeg / png / tiff)."""
    ext = _ENCODE_EXT.get(fmt.lower())
    if ext is None:
        raise UnsupportedImageError(f"Cannot encode to {fmt}")
    params: list[int] = []
    if ext == ".jpg":
        params = [cv2.IMWRITE_JPEG_QUALITY, int(quality)]
    ok, buffer = cv2.imencode(ext, image, params)
    if not ok:
        raise OSError(f"Failed to encode image as {fmt}")
    return buffer.tobytes()


def make_preview(image: np.ndarray, max_size: int = 512) -> np.ndarray:
    """Downscale so the longest edge is at most ``max_size`` px (no upscaling)."""
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= max_size:
        return image
    scale = max_size / longest
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)


def compute_histogram(image: np.ndarray) -> dict[str, list[int]]:
    """Return per-channel 256-bin histograms as ``{"r": [...], "g": [...], "b": [...]}``."""
    # image is BGR: channel 0 = B, 1 = G, 2 = R
    channels = {"b": 0, "g": 1, "r": 2}
    result: dict[str, list[int]] = {}
    for name, index in channels.items():
        hist = cv2.calcHist([image], [index], None, [256], [0, 256])
        result[name] = [int(v) for v in hist.flatten()]
    return {"r": result["r"], "g": result["g"], "b": result["b"]}
