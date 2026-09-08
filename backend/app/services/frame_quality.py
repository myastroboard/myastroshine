"""Per-frame quality scoring and auto-reject for the stacking pipeline.

Phase 3 of the stacking rebuild (``initial_plan/12_STACKING_REBUILD.md``). After
the registration pass has measured every frame (star count, star FWHM and
roundness, sky background, background noise, signal scale), :func:`score_frames`
turns those raw numbers into:

- a **score** (0-100) - a single "how good is this sub" figure for the UI;
- an integration **weight** (median frame = 1.0) for ``weighting = "quality"``;
- an **accept / reject** verdict against thresholds that scale with a
  ``quality_filter`` level (``off`` / ``lenient`` / ``moderate`` / ``strict``),
  each threshold relative to the stack's own median so it adapts to the night.

Everything is overridable: a rejected frame the user rescues, or a good frame
they drop, is handled by the manual include / exclude lists on the record - this
module only *suggests*.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

QUALITY_LEVELS = ("off", "lenient", "moderate", "strict")

_MIN_FRAMES_TO_JUDGE = 4  # below this the medians are too shaky to auto-reject anything
_WEIGHT_CLIP = (0.25, 4.0)
_SNR_CLIP = 3.0  # a frame's SNR ratio counts for at most 3x the median in the score
_TINY = 1e-12
_MAD_TO_SIGMA = 1.4826


@dataclass(frozen=True)
class FrameMeasure:
    """Raw per-frame measurements from the registration pass."""

    index: int
    star_count: int
    fwhm: float  # px, median star FWHM proxy (0 when no stars were found)
    roundness: float  # 0..1, 1 = round
    background: float  # linear sky level
    noise: float  # linear background noise
    scale: float  # linear signal scale (95th pct - background)


@dataclass(frozen=True)
class FrameQuality:
    """A scored frame: metrics for display plus the accept/reject verdict."""

    index: int
    star_count: int
    fwhm: float
    roundness: float
    background: float
    snr: float
    score: float  # 0..100
    weight: float  # relative integration weight, median frame ~= 1.0
    accepted: bool
    reject_reason: str | None  # "clouds" | "soft" | "trailed" | "bright_sky" | None


@dataclass(frozen=True)
class _Thresholds:
    min_star_ratio: float  # reject if star_count < this * median
    max_fwhm_ratio: float  # reject if fwhm > this * median
    min_roundness: float  # reject if median roundness < this (absolute)
    max_background_sigma: float  # reject if background > median + this * MAD


_LEVEL_THRESHOLDS = {
    "lenient": _Thresholds(0.35, 1.8, 0.45, 4.0),
    "moderate": _Thresholds(0.5, 1.5, 0.6, 3.0),
    "strict": _Thresholds(0.65, 1.3, 0.75, 2.0),
}


def score_frames(measures: Sequence[FrameMeasure], quality_filter: str) -> list[FrameQuality]:
    """Score every frame and, unless ``quality_filter`` is ``off`` or there are
    too few frames, flag the ones that fail the level's thresholds."""
    if not measures:
        return []

    stars = np.array([m.star_count for m in measures], dtype=np.float64)
    fwhm = np.array([m.fwhm for m in measures], dtype=np.float64)
    roundness = np.array([m.roundness for m in measures], dtype=np.float64)
    background = np.array([m.background for m in measures], dtype=np.float64)
    noise = np.array([max(m.noise, _TINY) for m in measures], dtype=np.float64)
    scale = np.array([m.scale for m in measures], dtype=np.float64)
    snr = scale / noise

    med_stars = max(float(np.median(stars)), 1.0)
    positive_fwhm = fwhm[fwhm > 0]
    med_fwhm = float(np.median(positive_fwhm)) if positive_fwhm.size else 0.0
    med_snr = max(float(np.median(snr)), _TINY)
    med_bg = float(np.median(background))
    mad_bg = _MAD_TO_SIGMA * float(np.median(np.abs(background - med_bg))) + _TINY

    # Integration weight: SNR^2 (photon statistics) tempered by star count and
    # sharpness, each clamped so one wild frame cannot dominate; normalised so
    # the median frame weighs ~1.
    raw_weight = (
        np.clip((snr / med_snr) ** 2, *_WEIGHT_CLIP)
        * np.clip(stars / med_stars, *_WEIGHT_CLIP)
        * (
            np.clip(med_fwhm / np.where(fwhm > 0, fwhm, med_fwhm or 1.0), *_WEIGHT_CLIP)
            if med_fwhm > 0
            else 1.0
        )
    )
    weight = raw_weight / max(float(np.median(raw_weight)), _TINY)

    # Score (0-100): SNR is the bulk of it, then star count, sharpness, roundness.
    snr_term = np.clip(snr / med_snr, 0.0, _SNR_CLIP) / _SNR_CLIP
    star_term = np.clip(stars / med_stars, 0.0, 1.5) / 1.5
    fwhm_term = np.clip(2.0 - fwhm / med_fwhm, 0.0, 1.0) if med_fwhm > 0 else np.ones_like(fwhm)
    score = 100.0 * np.clip(
        0.45 * snr_term + 0.25 * star_term + 0.2 * fwhm_term + 0.1 * roundness, 0.0, 1.0
    )

    thresholds = _LEVEL_THRESHOLDS.get(quality_filter)
    judge = thresholds is not None and len(measures) >= _MIN_FRAMES_TO_JUDGE

    out: list[FrameQuality] = []
    for i, m in enumerate(measures):
        reason: str | None = None
        if judge and thresholds is not None:
            reason = _reject_reason(
                thresholds,
                stars_ratio=stars[i] / med_stars,
                fwhm_ratio=(fwhm[i] / med_fwhm) if (med_fwhm > 0 and fwhm[i] > 0) else 1.0,
                roundness=roundness[i],
                background_sigma=(background[i] - med_bg) / mad_bg,
            )
        out.append(
            FrameQuality(
                index=m.index,
                star_count=m.star_count,
                fwhm=round(float(fwhm[i]), 2),
                roundness=round(float(roundness[i]), 3),
                background=round(float(background[i]), 5),
                snr=round(float(snr[i]), 2),
                score=round(float(score[i]), 1),
                weight=round(float(weight[i]), 3),
                accepted=reason is None,
                reject_reason=reason,
            )
        )
    return out


def _reject_reason(
    thresholds: _Thresholds,
    *,
    stars_ratio: float,
    fwhm_ratio: float,
    roundness: float,
    background_sigma: float,
) -> str | None:
    if stars_ratio < thresholds.min_star_ratio:
        return "clouds"
    if fwhm_ratio > thresholds.max_fwhm_ratio:
        return "soft"
    if roundness < thresholds.min_roundness:
        return "trailed"
    if background_sigma > thresholds.max_background_sigma:
        return "bright_sky"
    return None
