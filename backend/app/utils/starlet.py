"""Starlet (isotropic undecimated "a trous" B3-spline) wavelet tools.

The multiscale transform deep-sky tools are built on (Starck & Murtagh; PixInsight
MultiscaleLinearTransform, Siril's wavelets): an image is split into detail layers
``w_1 .. w_n`` - each twice the spatial scale of the previous - plus a smooth
residual ``c_n``, and ``image = c_n + sum(w_j)`` exactly. White noise lives mostly
in the finest layers with a known per-layer amplitude, so it can be thresholded
there without touching the larger-scale structure (nebulosity, galaxy arms) or
the stars (large coefficients survive a threshold untouched).

Everything here works on a single ``float32`` plane.
"""

from __future__ import annotations

import cv2
import numpy as np

_B3 = np.array([1.0, 4.0, 6.0, 4.0, 1.0], dtype=np.float32) / 16.0
#: Standard deviation of each starlet layer for unit-sigma white Gaussian noise
#: (Starck, Murtagh & Fadili, "Sparse Image and Signal Processing", table 6.1).
_NOISE_PER_LAYER = (0.889, 0.200, 0.086, 0.041, 0.020, 0.010, 0.005)
MAX_LAYERS = len(_NOISE_PER_LAYER)
_MAD_TO_SIGMA = 1.0 / 0.6745
_ABS_MEAN_TO_SIGMA = 1.2533  # sqrt(pi/2): E|x| of a Gaussian -> its sigma
_LOCAL_NOISE_SMOOTH = 6.0  # px, Gaussian window of the local noise estimate
_LOCAL_NOISE_RANGE = (0.5, 4.0)  # relative to the frame-wide noise
_TINY = 1e-12


def starlet_transform(plane: np.ndarray, layers: int) -> tuple[list[np.ndarray], np.ndarray]:
    """Decompose ``plane`` into ``layers`` detail layers and the smooth residual."""
    current: np.ndarray = plane.astype(np.float32, copy=False)
    details: list[np.ndarray] = []
    for level in range(layers):
        step = 2**level
        kernel = np.zeros(4 * step + 1, dtype=np.float32)
        kernel[::step] = _B3
        smoother = cv2.sepFilter2D(current, -1, kernel, kernel, borderType=cv2.BORDER_REFLECT)
        details.append(current - smoother)
        current = smoother
    return details, current


def noise_sigma(plane: np.ndarray) -> float:
    """Robust white-noise sigma of ``plane``, read off its finest starlet layer."""
    details, _ = starlet_transform(plane, 1)
    return float(np.median(np.abs(details[0]))) * _MAD_TO_SIGMA / _NOISE_PER_LAYER[0]


def denoise_plane(
    plane: np.ndarray, threshold: float, layers: int, *, local: bool = True
) -> np.ndarray:
    """Shrink each detail layer's noise-level coefficients; keep the residual as is.

    ``threshold`` is in noise sigmas (0 = identity, ~3 = strong). Each layer's
    threshold is ``threshold * sigma * noise_per_layer[j]``, applied with a
    non-negative garrote - coefficients near the noise level go to zero, strong
    ones (stars, filament edges) keep almost all of their amplitude, unlike a
    soft threshold which shaves every coefficient by the same amount and dims
    small stars. With ``local``, the threshold also follows a local noise map (the
    finest layer's smoothed energy), so a stretched frame's noisier background is
    smoothed harder than its brighter, relatively cleaner object.
    """
    if threshold <= 0.0:
        return plane
    layers = max(1, min(layers, MAX_LAYERS))
    details, result = starlet_transform(plane, layers)
    sigma = float(np.median(np.abs(details[0]))) * _MAD_TO_SIGMA / _NOISE_PER_LAYER[0]
    if sigma <= 0.0:
        return plane

    scale: np.ndarray | float = 1.0
    if local:
        energy = np.sqrt(cv2.GaussianBlur(details[0] * details[0], (0, 0), _LOCAL_NOISE_SMOOTH))
        reference = sigma * _NOISE_PER_LAYER[0] * _ABS_MEAN_TO_SIGMA
        scale = np.clip(energy / (reference + _TINY), *_LOCAL_NOISE_RANGE)

    result = result.copy()
    for level, detail in enumerate(details):
        cut = threshold * sigma * _NOISE_PER_LAYER[level] * scale
        keep = np.clip(1.0 - (cut * cut) / np.maximum(detail * detail, _TINY), 0.0, 1.0)
        result += detail * keep
    return result


def enhance_detail(plane: np.ndarray, amount: float, layers: int) -> np.ndarray:
    """Boost the ``layers`` finest detail layers by ``1 + amount``, noise excluded.

    Only coefficients well above the noise are boosted (the same garrote weight as
    :func:`denoise_plane`, at 3 sigma), so sharpening lifts stars and filaments
    without turning the background grain into sharpened grain - the failure mode
    of an unsharp mask or a Laplacian kernel on astro data.
    """
    if amount <= 0.0:
        return plane
    layers = max(1, min(layers, MAX_LAYERS))
    details, _ = starlet_transform(plane, layers)
    sigma = float(np.median(np.abs(details[0]))) * _MAD_TO_SIGMA / _NOISE_PER_LAYER[0]
    result = plane.astype(np.float32, copy=True)
    for level, detail in enumerate(details):
        cut = 3.0 * sigma * _NOISE_PER_LAYER[level]
        significant = np.clip(1.0 - (cut * cut) / np.maximum(detail * detail, _TINY), 0.0, 1.0)
        result += amount * detail * significant
    return result
