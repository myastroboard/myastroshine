"""Frame-quality scoring and auto-reject thresholds (Phase 3)."""

from __future__ import annotations

import pytest

from app.services.frame_quality import FrameMeasure, score_frames


def _good(index: int, **over: float) -> FrameMeasure:
    base = {
        "star_count": 100,
        "fwhm": 3.0,
        "roundness": 0.95,
        "background": 0.10,
        "noise": 0.01,
        "scale": 0.30,
    }
    base.update(over)
    return FrameMeasure(index=index, **base)  # type: ignore[arg-type]


def test_uniform_frames_all_pass_and_weigh_the_same() -> None:
    quals = score_frames([_good(i) for i in range(6)], "moderate")
    assert all(q.accepted for q in quals)
    assert all(q.reject_reason is None for q in quals)
    assert quals[0].weight == pytest.approx(1.0, abs=0.05)


def test_cloudy_frame_is_rejected_for_low_star_count() -> None:
    frames = [_good(i) for i in range(6)] + [_good(6, star_count=20, scale=0.08)]
    quals = {q.index: q for q in score_frames(frames, "moderate")}
    assert quals[6].reject_reason == "clouds"
    assert quals[6].accepted is False
    assert quals[0].accepted is True


def test_soft_frame_is_rejected_for_bloated_fwhm() -> None:
    frames = [_good(i) for i in range(6)] + [_good(6, fwhm=6.0)]
    quals = {q.index: q for q in score_frames(frames, "moderate")}
    assert quals[6].reject_reason == "soft"


def test_trailed_frame_is_rejected_for_low_roundness() -> None:
    frames = [_good(i) for i in range(6)] + [_good(6, roundness=0.4)]
    quals = {q.index: q for q in score_frames(frames, "moderate")}
    assert quals[6].reject_reason == "trailed"


def test_bright_sky_frame_is_rejected_for_background_outlier() -> None:
    frames = [_good(i) for i in range(6)] + [_good(6, background=0.5)]
    quals = {q.index: q for q in score_frames(frames, "moderate")}
    assert quals[6].reject_reason == "bright_sky"


def test_off_scores_but_never_rejects() -> None:
    frames = [_good(i) for i in range(6)] + [_good(6, star_count=5, fwhm=9.0, roundness=0.2)]
    quals = score_frames(frames, "off")
    assert all(q.accepted for q in quals)
    assert quals[-1].score < quals[0].score  # still scored lower


def test_too_few_frames_are_not_judged() -> None:
    frames = [_good(0), _good(1, star_count=3)]  # < _MIN_FRAMES_TO_JUDGE
    quals = score_frames(frames, "strict")
    assert all(q.accepted for q in quals)


def test_strict_rejects_what_lenient_keeps() -> None:
    frames = [_good(i) for i in range(6)] + [_good(6, fwhm=4.2)]  # 1.4x median
    lenient = {q.index: q for q in score_frames(frames, "lenient")}
    strict = {q.index: q for q in score_frames(frames, "strict")}
    assert lenient[6].accepted is True
    assert strict[6].accepted is False


def test_score_and_snr_track_the_inputs() -> None:
    frames = [_good(i) for i in range(5)] + [_good(5, noise=0.02)]  # half the SNR
    quals = {q.index: q for q in score_frames(frames, "off")}
    assert quals[5].snr == pytest.approx(15.0, abs=0.1)  # 0.30 / 0.02
    assert quals[5].score < quals[0].score
