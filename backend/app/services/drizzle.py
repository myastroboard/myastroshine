"""Variable-pixel linear reconstruction - "drizzle" (Fruchter & Hook 2002).

An undersampled, well-dithered stack is combined onto a finer output grid: each
input pixel is a square "drop" of side ``_PIXFRAC`` (< 1 sharpens), mapped through
the frame's registration transform, and its flux is area-distributed to the
output pixels it lands on. Accumulate ``flux`` and ``weight``; the result is
``flux / weight``.

The Seestar S50 samples at ~2.4"/px (mildly undersampled) and its alt-az field
rotation supplies the sub-pixel dither drizzle needs, so a 2x-3x drizzle can
recover real detail a plain resample cannot. It is opt-in (slower, and it
correlates neighbouring-pixel noise).
"""

from __future__ import annotations

import numpy as np

_PIXFRAC = 0.7
_TINY = 1e-12
_HALF = 0.5  # pixel-centre convention: cell C spans [C - 0.5, C + 0.5]


def drizzle_accumulate(
    frame: np.ndarray,
    matrix: np.ndarray,
    scale: int,
    frame_weight: float,
    flux: np.ndarray,
    weight: np.ndarray,
    keep: np.ndarray | None = None,
) -> None:
    """Drop one ``(h, w, 3)`` frame into the ``(h*scale, w*scale, ...)`` accumulators.

    ``matrix`` (2x3) maps full-resolution frame pixel centres to full-resolution
    1x reference pixel centres; ``keep`` (``(h, w)`` bool) masks rejected input
    pixels. ``flux`` is ``(H, W, 3)`` and ``weight`` is ``(H, W)``, both float32.
    """
    height_in, width_in = frame.shape[:2]
    out_h, out_w = flux.shape[:2]

    ys, xs = np.mgrid[0:height_in, 0:width_in]
    xs = xs.astype(np.float32)
    ys = ys.astype(np.float32)
    x_out = (matrix[0, 0] * xs + matrix[0, 1] * ys + matrix[0, 2]) * scale
    y_out = (matrix[1, 0] * xs + matrix[1, 1] * ys + matrix[1, 2]) * scale

    half = _PIXFRAC * scale / 2.0
    x_lo, x_hi = x_out - half, x_out + half
    y_lo, y_hi = y_out - half, y_out + half

    mask = np.ones((height_in, width_in), dtype=bool) if keep is None else keep.astype(bool)
    mask &= (x_hi > -_HALF) & (x_lo < out_w - _HALF) & (y_hi > -_HALF) & (y_lo < out_h - _HALF)
    if not mask.any():
        return

    x_lo, x_hi = x_lo[mask], x_hi[mask]
    y_lo, y_hi = y_lo[mask], y_hi[mask]
    values = frame[mask].astype(np.float32)  # (N, 3)

    # Splat onto the 2x2 output cells nearest the drop centre. When the drop
    # (side pixfrac*scale) spills past that 2x2 the missing area is dropped, but
    # from *both* flux and weight - the ``flux / weight`` result stays unbiased.
    col0 = np.floor(x_lo + 0.5).astype(np.int64)
    row0 = np.floor(y_lo + 0.5).astype(np.int64)
    flux_flat = flux.reshape(-1, 3)
    weight_flat = weight.reshape(-1)
    cells = out_h * out_w

    for d_row in range(2):
        rows = row0 + d_row
        overlap_y = np.clip(np.minimum(y_hi, rows + 0.5) - np.maximum(y_lo, rows - 0.5), 0.0, None)
        row_ok = (rows >= 0) & (rows < out_h) & (overlap_y > 0)
        for d_col in range(2):
            cols = col0 + d_col
            overlap_x = np.clip(
                np.minimum(x_hi, cols + 0.5) - np.maximum(x_lo, cols - 0.5), 0.0, None
            )
            selected = row_ok & (cols >= 0) & (cols < out_w) & (overlap_x > 0)
            if not selected.any():
                continue
            area = (overlap_x[selected] * overlap_y[selected] * frame_weight).astype(np.float32)
            index = rows[selected] * out_w + cols[selected]
            for channel in range(3):
                flux_flat[:, channel] += np.bincount(
                    index, weights=values[selected, channel] * area, minlength=cells
                ).astype(np.float32)
            weight_flat += np.bincount(index, weights=area, minlength=cells).astype(np.float32)


def drizzle_finalise(
    flux: np.ndarray, weight: np.ndarray, typical_weight: float
) -> tuple[np.ndarray, np.ndarray]:
    """``flux / weight`` plus an integer per-pixel coverage map (frames-equivalent)."""
    composite = (flux / np.maximum(weight[..., np.newaxis], _TINY)).astype(np.float32)
    composite[weight <= _TINY] = 0.0
    coverage = np.rint(weight / max(typical_weight, _TINY)).astype(np.int32)
    return np.clip(composite, 0.0, None), coverage
