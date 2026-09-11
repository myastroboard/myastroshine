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
