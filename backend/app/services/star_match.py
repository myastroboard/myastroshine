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
