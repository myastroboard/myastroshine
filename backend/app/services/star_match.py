"""StarMatchService - align two star fields by asterism (triangle) matching.

Takes two sets of star centroids and finds the geometric transform
(translation / similarity / affine) that maps one onto the other. Vendored
triangle-matching in the style of ``astroalign``: build a rotation- and
scale-invariant descriptor per triangle (the ratios of its sorted side
lengths), match descriptors between the two frames to get candidate point
correspondences, then fit the transform with RANSAC. No scipy, no new
dependency - numpy brute-force over the ~60 brightest stars is fast enough.

The caller (``StackingService``) does the star detection and passes the
centroids sorted brightest-first.

:func:`refine_warp` then optionally replaces the global transform by a smooth
polynomial warp fitted on *every* star pair - a wide-angle lens' distortion
makes stars drift differently across the field as the sky turns, which no
single rotation + shift + scale can follow.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from app.logging_config import get_logger

logger = get_logger(__name__)

_MAX_STARS = 60  # match on the N brightest; more is slower, not more accurate
_NEIGHBOURS = 6  # build triangles from each star's k nearest neighbours
_INVARIANT_TOL = 0.02  # max L2 distance between two triangle descriptors to pair them
_MIN_SIDE_RATIO = 0.15  # skip near-collinear triangles (unstable descriptor)
_MIN_TRIANGLES = 1
_RANSAC_REPROJ = 3.0  # px
_MIN_INLIERS = 6
_MAX_RMS = 2.0  # px; an inlier residual RMS above this is a failed alignment
_MAX_CANDIDATES = 3000  # cap correspondences fed to RANSAC
_MIN_STARS = 3
_DEGENERATE_SIDE = 1e-6
# refine_warp (see its docstring).
_WARP_DEGREE = 3
_WARP_PAIR_RADIUS = 3.0  # px: a star pair is matched within this after the global transform
_WARP_MIN_PAIRS = 60  # 10 coefficients per axis: plenty of pairs, or no refinement
_WARP_COVERAGE_CELLS = 3  # the frame split into 3 x 3 cells ...
_WARP_MIN_COVERED = 7  # ... at least this many must hold pairs (no blind extrapolation)
_WARP_MIN_CELL_PAIRS = 4
_WARP_REJECT_ITERATIONS = 3
_WARP_REJECT_SIGMA = 3.0
_WARP_MIN_GAIN = 0.8  # the warp must cut the global transform's residual by >= 20%
_WARP_MAX_DEVIATION = 0.02  # ... and stay within 2% of the frame diagonal of it, everywhere
_WARP_CHECK_GRID = 17
_WARP_CHUNK = 512  # brute-force nearest-neighbour block size
_SCALE_RANGE = (
    0.5,
    2.0,
)  # frames from one session are within a few % scale; guards degenerate fits


@dataclass(frozen=True)
class Alignment:
    """The transform mapping the source star field onto the target one."""

    matrix: np.ndarray | None  # 2x3 affine; ``None`` when matching failed
    inliers: int
    rms: float
    candidates: int  # point correspondences found before RANSAC

    @property
    def ok(self) -> bool:
        return self.matrix is not None


@dataclass(frozen=True)
class PolyWarp:
    """A smooth warp from reference-frame pixels to source-frame pixels.

    Coordinates are in the registration frame (``width`` x ``height``, the
    half-resolution image star centroids were measured on); the polynomial takes
    them normalised to ``[0, 1]``. It maps the *reference* grid to the *source*
    (the direction ``cv2.remap`` needs). ``rms`` is the residual over the star
    pairs, in source pixels.
    """

    coeffs_x: np.ndarray
    coeffs_y: np.ndarray
    width: int
    height: int
    rms: float

    def source_coords(self, xs: np.ndarray, ys: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Source pixel coordinates for reference pixel coordinates ``(xs, ys)``."""
        terms = _warp_terms(xs / self.width, ys / self.height)
        return terms @ self.coeffs_x, terms @ self.coeffs_y

    def remap_maps(self, width: int, height: int, step: int = 8) -> tuple[np.ndarray, np.ndarray]:
        """``cv2.remap`` maps for an output of ``width`` x ``height`` pixels.

        The output may be a higher resolution than the registration frame (the
        align pass works at full resolution): coordinates are scaled by the
        resolution ratio. The polynomial is smooth, so it is evaluated every
        ``step`` pixels and interpolated.
        """
        scale_x, scale_y = width / self.width, height / self.height
        # Coarse samples at output pixels 0, step, 2 step, ... (one past the edge).
        grid_x = np.arange(0, width + step, step, dtype=np.float64)
        grid_y = np.arange(0, height + step, step, dtype=np.float64)
        xx, yy = np.meshgrid(grid_x, grid_y)
        src_x, src_y = self.source_coords(xx.ravel() / scale_x, yy.ravel() / scale_y)
        coarse_x = (src_x * scale_x).reshape(xx.shape).astype(np.float32)
        coarse_y = (src_y * scale_y).reshape(xx.shape).astype(np.float32)
        # Output pixel p lies at coarse index p / step: bilinear lookup there.
        lookup_x, lookup_y = np.meshgrid(
            np.arange(width, dtype=np.float32) / step, np.arange(height, dtype=np.float32) / step
        )
        map_x = cv2.remap(coarse_x, lookup_x, lookup_y, cv2.INTER_LINEAR)
        map_y = cv2.remap(coarse_y, lookup_x, lookup_y, cv2.INTER_LINEAR)
        return map_x, map_y


class StarMatchService:
    """Aligns a source star field onto a target one via triangle matching."""

    def align(
        self, source: np.ndarray, target: np.ndarray, transform: str = "similarity"
    ) -> Alignment:
        """Estimate the transform from ``source`` centroids to ``target`` centroids.

        Both are ``(N, 2)`` ``(x, y)`` arrays, sorted brightest-first.
        ``transform`` is ``translation`` (shift only), ``similarity`` (shift +
        rotation + uniform scale) or ``affine`` (adds shear/aspect).
        """
        src = np.asarray(source, dtype=np.float64)[:_MAX_STARS]
        tgt = np.asarray(target, dtype=np.float64)[:_MAX_STARS]
        if len(src) < _MIN_STARS or len(tgt) < _MIN_STARS:
            return Alignment(None, 0, math.inf, 0)

        inv_s, verts_s = _triangle_descriptors(src)
        inv_t, verts_t = _triangle_descriptors(tgt)
        if len(inv_s) < _MIN_TRIANGLES or len(inv_t) < _MIN_TRIANGLES:
            return Alignment(None, 0, math.inf, 0)

        src_pts, dst_pts = _candidate_pairs(src, tgt, inv_s, verts_s, inv_t, verts_t)
        if len(src_pts) < _MIN_INLIERS:
            return Alignment(None, 0, math.inf, len(src_pts))
        return _fit(np.array(src_pts), np.array(dst_pts), transform)


def refine_warp(
    source: np.ndarray, target: np.ndarray, matrix: np.ndarray, shape: tuple[int, int]
) -> PolyWarp | None:
    """Refine a global transform into a polynomial warp fitted on every star pair.

    ``source`` / ``target`` are all the detected centroids ``(N, 2)`` of the frame
    and of the reference; ``matrix`` is the global source -> reference transform
    (from :meth:`StarMatchService.align`); ``shape`` is ``(height, width)``.

    Each projected source star is paired with its mutual nearest reference star
    within ``_WARP_PAIR_RADIUS``; a cubic polynomial reference -> source is fitted
    with iterative ``_WARP_REJECT_SIGMA`` MAD rejection. On a real iPhone series
    (24 mm equivalent, 4 minutes apart) this cut the residual from 1.65 to
    0.49-0.69 px over ~1500 pairs - the global transform's error grew toward the
    field edges, the signature of lens distortion.

    ``None`` (keep the global transform) unless there are enough pairs, spread
    over most of the frame, the warp cuts the global residual by at least 20%,
    and it nowhere strays more than ``_WARP_MAX_DEVIATION`` of the diagonal from
    the global transform - a deep-sky field (no distortion, few stars) keeps
    its exact behaviour.
    """
    height, width = shape
    src = np.asarray(source, dtype=np.float64).reshape(-1, 2)
    tgt = np.asarray(target, dtype=np.float64).reshape(-1, 2)
    if len(src) < _WARP_MIN_PAIRS or len(tgt) < _WARP_MIN_PAIRS:
        return None
    projected = src @ matrix[:, :2].T + matrix[:, 2]
    pairs = _mutual_nearest(projected, tgt, _WARP_PAIR_RADIUS)
    if len(pairs) < _WARP_MIN_PAIRS or not _well_spread(tgt[pairs[:, 1]], width, height):
        return None
    src_pts, ref_pts = src[pairs[:, 0]], tgt[pairs[:, 1]]

    terms = _warp_terms(ref_pts[:, 0] / width, ref_pts[:, 1] / height)
    keep = np.ones(len(ref_pts), dtype=bool)
    for _ in range(_WARP_REJECT_ITERATIONS):
        coeffs_x, *_ = np.linalg.lstsq(terms[keep], src_pts[keep, 0], rcond=None)
        coeffs_y, *_ = np.linalg.lstsq(terms[keep], src_pts[keep, 1], rcond=None)
        residual = np.hypot(terms @ coeffs_x - src_pts[:, 0], terms @ coeffs_y - src_pts[:, 1])
        spread = float(np.median(np.abs(residual[keep] - np.median(residual[keep])))) * 1.4826
        keep = residual <= float(np.median(residual[keep])) + _WARP_REJECT_SIGMA * spread
        if keep.sum() < _WARP_MIN_PAIRS:
            return None
    warp_rms = float(np.sqrt(np.mean(residual[keep] ** 2)))

    inverse = cv2.invertAffineTransform(matrix.astype(np.float64))
    global_src = ref_pts @ inverse[:, :2].T + inverse[:, 2]
    global_rms = float(np.sqrt(np.mean(np.sum((global_src - src_pts)[keep] ** 2, axis=1))))
    if warp_rms > _WARP_MIN_GAIN * global_rms:
        return None

    warp = PolyWarp(coeffs_x, coeffs_y, width, height, warp_rms)
    grid_x, grid_y = np.meshgrid(
        np.linspace(0, width, _WARP_CHECK_GRID), np.linspace(0, height, _WARP_CHECK_GRID)
    )
    grid = np.stack([grid_x.ravel(), grid_y.ravel()], axis=1)
    warped_x, warped_y = warp.source_coords(grid[:, 0], grid[:, 1])
    expected = grid @ inverse[:, :2].T + inverse[:, 2]
    deviation = float(np.max(np.hypot(warped_x - expected[:, 0], warped_y - expected[:, 1])))
    if deviation > _WARP_MAX_DEVIATION * math.hypot(width, height):
        logger.info("polynomial warp rejected", deviation=round(deviation, 1))
        return None
    return warp


def _warp_terms(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """The ``x^i y^j`` (``i + j <= _WARP_DEGREE``) design-matrix columns."""
    x, y = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    return np.stack(
        [x**i * y**j for i in range(_WARP_DEGREE + 1) for j in range(_WARP_DEGREE + 1 - i)],
        axis=-1,
    )


def _mutual_nearest(a: np.ndarray, b: np.ndarray, radius: float) -> np.ndarray:
    """Index pairs ``(i, j)`` where ``a[i]`` and ``b[j]`` are each other's nearest
    neighbour and closer than ``radius``. Brute force in blocks - a few thousand
    stars each, no KD-tree needed."""
    nearest_b = np.empty(len(a), dtype=np.int64)
    dist_b = np.empty(len(a))
    for start in range(0, len(a), _WARP_CHUNK):
        block = a[start : start + _WARP_CHUNK]
        d2 = ((block[:, None, :] - b[None, :, :]) ** 2).sum(axis=2)
        nearest_b[start : start + len(block)] = d2.argmin(axis=1)
        dist_b[start : start + len(block)] = np.sqrt(d2.min(axis=1))
    nearest_a = np.empty(len(b), dtype=np.int64)
    for start in range(0, len(b), _WARP_CHUNK):
        block = b[start : start + _WARP_CHUNK]
        d2 = ((block[:, None, :] - a[None, :, :]) ** 2).sum(axis=2)
        nearest_a[start : start + len(block)] = d2.argmin(axis=1)
    i = np.flatnonzero((dist_b <= radius) & (nearest_a[nearest_b] == np.arange(len(a))))
    return np.stack([i, nearest_b[i]], axis=1)


def _well_spread(points: np.ndarray, width: int, height: int) -> bool:
    """True when the pairs cover most of a 3 x 3 split of the frame."""
    cells = _WARP_COVERAGE_CELLS
    col = np.clip((points[:, 0] / width * cells).astype(int), 0, cells - 1)
    row = np.clip((points[:, 1] / height * cells).astype(int), 0, cells - 1)
    counts = np.bincount(row * cells + col, minlength=cells * cells)
    return int((counts >= _WARP_MIN_CELL_PAIRS).sum()) >= _WARP_MIN_COVERED


def _fit(src_arr: np.ndarray, dst_arr: np.ndarray, transform: str) -> Alignment:
    """RANSAC-fit ``transform`` to the candidate correspondences and sanity-check it."""
    candidates = len(src_arr)
    estimator = cv2.estimateAffine2D if transform == "affine" else cv2.estimateAffinePartial2D
    matrix, mask = estimator(
        src_arr, dst_arr, method=cv2.RANSAC, ransacReprojThreshold=_RANSAC_REPROJ
    )
    if matrix is None or mask is None:
        return Alignment(None, 0, math.inf, candidates)

    keep = mask.ravel().astype(bool)
    inliers = int(keep.sum())
    scale = math.sqrt(abs(float(np.linalg.det(matrix[:, :2]))))
    projected = (matrix[:, :2] @ src_arr[keep].T).T + matrix[:, 2]
    rms = (
        float(np.sqrt(((projected - dst_arr[keep]) ** 2).sum(axis=1).mean()))
        if inliers
        else math.inf
    )

    if inliers < _MIN_INLIERS or rms > _MAX_RMS or not _SCALE_RANGE[0] <= scale <= _SCALE_RANGE[1]:
        return Alignment(None, inliers, rms, candidates)

    if transform == "translation":
        shift = np.median(dst_arr[keep] - src_arr[keep], axis=0)
        matrix = np.array([[1.0, 0.0, shift[0]], [0.0, 1.0, shift[1]]])
    return Alignment(matrix, inliers, rms, candidates)


def _triangle_descriptors(stars: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """``(descriptors (M, 2), vertex_indices (M, 3))`` for triangles built from
    each star's nearest neighbours.

    The descriptor is ``(mid_side / long_side, short_side / long_side)`` - a
    translation-, rotation- and scale-invariant fingerprint of the triangle
    shape. Vertices are ordered by opposite-side length (longest first) so two
    matching triangles' vertices line up positionally.
    """
    n = len(stars)
    dist = np.sqrt(((stars[:, None, :] - stars[None, :, :]) ** 2).sum(axis=-1))
    k = min(_NEIGHBOURS, n - 1)
    neighbours = np.argsort(dist, axis=1)[:, 1 : k + 1]

    seen: set[tuple[int, ...]] = set()
    descriptors: list[tuple[float, float]] = []
    vertices: list[np.ndarray] = []
    for i in range(n):
        for a in range(k):
            for b in range(a + 1, k):
                tri = tuple(sorted((i, int(neighbours[i, a]), int(neighbours[i, b]))))
                if tri in seen:
                    continue
                seen.add(tri)
                p, q, r = tri
                sides = np.array([dist[q, r], dist[p, r], dist[p, q]])  # opposite p, q, r
                order = np.argsort(-sides)
                ordered = sides[order]
                if ordered[0] <= _DEGENERATE_SIDE or ordered[2] / ordered[0] < _MIN_SIDE_RATIO:
                    continue
                descriptors.append((ordered[1] / ordered[0], ordered[2] / ordered[0]))
                vertices.append(np.array([p, q, r])[order])

    if not descriptors:
        return np.empty((0, 2)), np.empty((0, 3), dtype=int)
    return np.array(descriptors), np.array(vertices)


def _candidate_pairs(
    src: np.ndarray,
    tgt: np.ndarray,
    inv_s: np.ndarray,
    verts_s: np.ndarray,
    inv_t: np.ndarray,
    verts_t: np.ndarray,
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Point correspondences from every source triangle whose descriptor has a
    close-enough match among the target triangles."""
    gaps = np.sqrt(((inv_s[:, None, :] - inv_t[None, :, :]) ** 2).sum(axis=-1))
    nearest = gaps.argmin(axis=1)
    nearest_gap = gaps[np.arange(len(inv_s)), nearest]

    src_pts: list[np.ndarray] = []
    dst_pts: list[np.ndarray] = []
    for si in np.argsort(nearest_gap):
        if nearest_gap[si] > _INVARIANT_TOL or len(src_pts) >= _MAX_CANDIDATES:
            break
        ti = nearest[si]
        for vs, vt in zip(verts_s[si], verts_t[ti], strict=True):
            src_pts.append(src[vs])
            dst_pts.append(tgt[vt])
    return src_pts, dst_pts
