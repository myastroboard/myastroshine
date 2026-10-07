"""Starlet (isotropic undecimated "a trous" B3-spline) wavelet tools.

The multiscale transform deep-sky tools are built on (Starck & Murtagh; PixInsight
MultiscaleLinearTransform, Siril's wavelets): an image is split into detail layers
``w_1 .. w_n`` - each twice the spatial scale of the previous - plus a smooth
residual ``c_n``, and ``image = c_n + sum(w_j)`` exactly. White noise lives mostly
in the finest layers with a known per-layer amplitude, so it can be thresholded
there without touching the larger-scale structure (nebulosity, galaxy arms) or
the stars (large coefficients survive a threshold untouched).

Real astro data is rarely white noise, though: debayering, the sub-pixel
registration of every stacked frame and JPEG compression all correlate the noise
over a pixel or two, which drains the finest layer. On real Seestar stacks the
second layer carried 3-7x the noise the white-noise model predicts from the
first, so thresholds extrapolated from the first left the coarser grain and the
colour mottle untouched. :func:`layer_noise` scales the model from whichever of
the two finest layers reads the higher noise.

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
_LOCAL_NOISE_CAP = 3.0  # noise sigmas: a larger coefficient is signal, not local noise
_TINY = 1e-12


def _garrote_weight(detail: np.ndarray, cut_sq: np.ndarray | float, out: np.ndarray) -> np.ndarray:
    """``clip(1 - cut^2 / detail^2, 0, 1)`` - the non-negative garrote weight - into ``out``.

    Computed in place: on a full-res frame, the expression's temporaries (one
    24 MP array per operator) cost more than the arithmetic itself.
    """
    np.multiply(detail, detail, out=out)
    np.maximum(out, _TINY, out=out)
    np.divide(cut_sq, out, out=out)
    np.subtract(1.0, out, out=out)
    np.clip(out, 0.0, 1.0, out=out)
    return out


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


def layer_noise(details: list[np.ndarray]) -> list[float]:
    """Noise sigma of each detail layer of a starlet decomposition.

    The finest layer reads its own (robust) noise. The coarser layers follow the
    white-noise model, scaled from whichever of the two finest layers reads the
    higher noise: a short-range correlation (debayering, registration
    interpolation) mostly drains the finest layer, so the second one is the
    better measure of the noise the coarser scales carry. Coarser layers are not
    measured themselves - there, faint stars and nebulosity outweigh the noise and
    a measurement read them as noise (a dense star field came out blurred).
    """
    finest = float(np.median(np.abs(details[0]))) * _MAD_TO_SIGMA
    sigma = finest / _NOISE_PER_LAYER[0]
    if len(details) > 1:
        second = float(np.median(np.abs(details[1][::2, ::2]))) * _MAD_TO_SIGMA
        sigma = max(sigma, second / _NOISE_PER_LAYER[1])
    return [finest] + [sigma * _NOISE_PER_LAYER[level] for level in range(1, len(details))]


def noise_sigma(plane: np.ndarray) -> float:
    """Robust white-noise sigma of ``plane``, read off its finest starlet layer."""
    details, _ = starlet_transform(plane, 1)
    return float(np.median(np.abs(details[0]))) * _MAD_TO_SIGMA / _NOISE_PER_LAYER[0]


def denoise_plane(
    plane: np.ndarray, threshold: float, layers: int, *, local: bool = True
) -> np.ndarray:
    """Shrink each detail layer's noise-level coefficients; keep the residual as is.

    ``threshold`` is in noise sigmas (0 = identity, ~3 = strong). Each layer's
    threshold is ``threshold`` times that layer's noise (:func:`layer_noise`),
    applied with a non-negative garrote - coefficients near the noise level go to
    zero, strong ones (stars, filament edges) keep almost all of their amplitude,
    unlike a soft threshold which shaves every coefficient by the same amount and
    dims small stars. With ``local``, the threshold also follows a local noise map
    (the finest layer's smoothed energy), so a stretched frame's noisier background
    is smoothed harder than its brighter, relatively cleaner object.
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
        # Each coefficient is capped at a few noise sigma first: a star is signal,
        # not noise, and uncapped it raised the threshold all round itself - up to
        # the 4x ceiling - so the denoise ate into the stars it is meant to spare.
        capped = np.minimum(np.abs(details[0]), _LOCAL_NOISE_CAP * sigma * _NOISE_PER_LAYER[0])
        energy = np.sqrt(cv2.GaussianBlur(capped * capped, (0, 0), _LOCAL_NOISE_SMOOTH))
        reference = sigma * _NOISE_PER_LAYER[0] * _ABS_MEAN_TO_SIGMA
        scale = np.clip(energy / (reference + _TINY), *_LOCAL_NOISE_RANGE)

    result = result.copy()
    scratch = np.empty_like(result)
    for detail, level_sigma in zip(details, layer_noise(details), strict=True):
        cut = threshold * level_sigma * scale
        keep = _garrote_weight(detail, cut * cut, scratch)
        keep *= detail
        result += keep
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
    result = plane.astype(np.float32, copy=True)
    scratch = np.empty_like(result)
    for detail, level_sigma in zip(details, layer_noise(details), strict=True):
        cut = 3.0 * level_sigma
        significant = _garrote_weight(detail, cut * cut, scratch)
        result += amount * detail * significant
    return result
