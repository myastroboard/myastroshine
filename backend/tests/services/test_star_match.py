"""StarMatchService: recover a known transform between two star fields."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.services import star_match
from app.services.star_match import StarMatchService, _fit


def _star_field(n: int = 40, size: int = 1000, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.uniform(50, size - 50, size=(n, 2))


def _apply(stars: np.ndarray, angle_deg: float, scale: float, tx: float, ty: float) -> np.ndarray:
    rad = math.radians(angle_deg)
    rot = scale * np.array([[math.cos(rad), -math.sin(rad)], [math.sin(rad), math.cos(rad)]])
    return (rot @ stars.T).T + np.array([tx, ty])


@pytest.fixture
def matcher() -> StarMatchService:
    return StarMatchService()


def test_recovers_a_pure_translation(matcher: StarMatchService) -> None:
    ref = _star_field()
    moved = _apply(ref, angle_deg=0.0, scale=1.0, tx=17.0, ty=-9.0)

    result = matcher.align(moved, ref, transform="translation")

    assert result.ok
    projected = (result.matrix[:, :2] @ moved.T).T + result.matrix[:, 2]
    assert np.abs(projected - ref).max() < 0.5


def test_recovers_rotation_and_scale(matcher: StarMatchService) -> None:
    ref = _star_field(seed=3)
    moved = _apply(ref, angle_deg=12.0, scale=1.05, tx=-30.0, ty=25.0)

    result = matcher.align(moved, ref, transform="similarity")

    assert result.ok
    assert result.rms < 1.0
    projected = (result.matrix[:, :2] @ moved.T).T + result.matrix[:, 2]
    assert np.abs(projected - ref).max() < 1.5


def test_survives_missing_and_spurious_stars(matcher: StarMatchService) -> None:
    """A few stars dropped from one frame and a few noise detections added
    still leaves the transform recoverable (RANSAC rejects the outliers)."""
    rng = np.random.default_rng(7)
    ref = _star_field(n=50, seed=7)
    moved = _apply(ref, angle_deg=6.0, scale=1.0, tx=8.0, ty=8.0)
    moved = moved[5:]  # first 5 stars not detected this frame
    moved = np.vstack([moved, rng.uniform(0, 1000, size=(6, 2))])  # 6 fake detections

    result = matcher.align(moved, ref, transform="similarity")

    assert result.ok
    assert result.inliers >= 10


def test_unrelated_fields_do_not_align(matcher: StarMatchService) -> None:
    result = matcher.align(_star_field(seed=1), _star_field(seed=99), transform="similarity")
    assert not result.ok


def test_too_few_stars_fails_cleanly(matcher: StarMatchService) -> None:
    result = matcher.align(np.array([[1.0, 2.0], [3.0, 4.0]]), _star_field(), "similarity")
    assert not result.ok
    assert result.matrix is None


def test_extremely_unevenly_spaced_stars_form_no_usable_triangle(
    matcher: StarMatchService,
) -> None:
    """Enough stars to pass the count check (exactly 3, one possible triangle),
    but so unevenly spaced (near-collinear by the side-length-ratio heuristic)
    that it is filtered as degenerate - nothing left to match on at all."""
    sliver = np.array([[0.0, 0.0], [1.0, 0.0], [1000.0, 0.0]], dtype=np.float64)

    result = matcher.align(sliver, sliver, transform="similarity")

    assert not result.ok
    assert result.candidates == 0


def test_too_few_candidate_correspondences_fails_cleanly(matcher: StarMatchService) -> None:
    """Exactly 3 stars form at most one triangle -> at most 3 point
    correspondences, always below _MIN_INLIERS - never enough to even attempt
    a RANSAC fit."""
    triangle = np.array([[0.0, 0.0], [100.0, 0.0], [40.0, 80.0]])

    result = matcher.align(triangle, triangle, transform="similarity")

    assert not result.ok
    assert result.candidates < 6


def test_fit_reports_no_alignment_when_the_cv2_estimator_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cv2's RANSAC estimator can itself return (None, None) on a degenerate
    input - the fit is reported as failed rather than raising."""
    monkeypatch.setattr(star_match.cv2, "estimateAffinePartial2D", lambda *_a, **_k: (None, None))
    points = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0], [3.0, 3.0], [4.0, 4.0], [5.0, 5.0]])

    result = _fit(points, points.copy(), "similarity")

    assert not result.ok
    assert result.candidates == 6


# -- refine_warp: a polynomial warp for wide-angle distortion ---------------

_W, _H = 600, 800


def _field(count: int = 900, seed: int = 5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.column_stack([rng.uniform(0, _W, count), rng.uniform(0, _H, count)])


def _distort(points: np.ndarray, k: float) -> np.ndarray:
    """Radial (barrel / pincushion) distortion about the frame centre."""
    centre = np.array([_W / 2, _H / 2])
    offset = points - centre
    r2 = (offset**2).sum(axis=1, keepdims=True) / (np.hypot(_W, _H) / 2) ** 2
    return centre + offset * (1 + k * r2)


def _shifted_distorted_pair(k: float, seed: int = 5) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A reference field and the same sky shifted by 40 px then seen through a
    lens with distortion ``k`` in both frames - the sky moved, the lens did not,
    so the frames differ by more than a rigid transform. Returns
    ``(source, reference, global_matrix)``."""
    sky = _field(seed=seed)
    reference = _distort(sky, k)
    source = _distort(sky + np.array([40.0, 0.0]), k)
    keep = (source[:, 0] > 0) & (source[:, 0] < _W) & (reference[:, 0] > 0) & (reference[:, 0] < _W)
    source, reference = source[keep], reference[keep]
    matrix = np.array([[1.0, 0.0, -40.0], [0.0, 1.0, 0.0]])  # the best global guess
    return source, reference, matrix


def test_refine_warp_follows_lens_distortion_a_rigid_transform_cannot() -> None:
    """With a distorted wide field, the warp maps every reference star back onto
    its source star far better than the global shift."""
    source, reference, matrix = _shifted_distorted_pair(k=0.04)
    warp = star_match.refine_warp(source, reference, matrix, (_H, _W))
    assert warp is not None
    src_x, src_y = warp.source_coords(reference[:, 0], reference[:, 1])
    error = np.hypot(src_x - source[:, 0], src_y - source[:, 1])
    rigid = np.hypot(reference[:, 0] + 40.0 - source[:, 0], reference[:, 1] - source[:, 1])
    assert float(np.sqrt(np.mean(error**2))) < 0.2 * float(np.sqrt(np.mean(rigid**2)))
    assert warp.rms < 0.3


def test_refine_warp_keeps_the_global_transform_when_it_is_already_right() -> None:
    """No distortion: the warp cannot beat the global transform by 20%, so None."""
    sky = _field()
    rng = np.random.default_rng(1)
    source = sky + rng.normal(0, 0.1, sky.shape)
    matrix = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    assert star_match.refine_warp(source, sky, matrix, (_H, _W)) is None


def test_refine_warp_needs_enough_well_spread_stars() -> None:
    """Too few stars, or stars bunched in one part of the frame, give no warp."""
    source, reference, matrix = _shifted_distorted_pair(k=0.04)
    assert star_match.refine_warp(source[:40], reference[:40], matrix, (_H, _W)) is None
    top = reference[:, 1] < _H / 3
    assert star_match.refine_warp(source[top], reference[top], matrix, (_H, _W)) is None


def test_refine_warp_rejects_a_warp_straying_far_from_the_global_transform() -> None:
    """A fit implying a huge deviation from the global transform is not trusted."""
    source, reference, matrix = _shifted_distorted_pair(k=0.04)
    original = star_match._WARP_MAX_DEVIATION
    try:
        star_match._WARP_MAX_DEVIATION = 0.0001
        assert star_match.refine_warp(source, reference, matrix, (_H, _W)) is None
    finally:
        star_match._WARP_MAX_DEVIATION = original


def test_warp_remap_maps_scale_to_a_larger_output() -> None:
    """The maps for a 2x output are the warp evaluated at half the coordinates,
    times two - the align pass works at full resolution, registration at half."""
    source, reference, matrix = _shifted_distorted_pair(k=0.04)
    warp = star_match.refine_warp(source, reference, matrix, (_H, _W))
    assert warp is not None
    map_x, map_y = warp.remap_maps(2 * _W, 2 * _H)
    assert map_x.shape == (2 * _H, 2 * _W)
    for x, y in ((0, 0), (601, 333), (1199, 1599)):
        sx, sy = warp.source_coords(np.array([x / 2]), np.array([y / 2]))
        assert abs(float(map_x[y, x]) - 2 * float(sx[0])) < 0.05
        assert abs(float(map_y[y, x]) - 2 * float(sy[0])) < 0.05
