"""Small helpers shared across test modules."""

from __future__ import annotations

import cv2
import numpy as np


def translate(image: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """Shift ``image`` by ``(dx, dy)`` pixels, keeping its size."""
    matrix = np.array([[1.0, 0.0, dx], [0.0, 1.0, dy]], dtype=np.float32)
    return cv2.warpAffine(image, matrix, (image.shape[1], image.shape[0]))


def png_bytes(image: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", image)
    assert ok
    return buffer.tobytes()
