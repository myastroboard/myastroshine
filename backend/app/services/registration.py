"""RegistrationService - align multiple frames onto a reference (v1.1).

Feature detection (ORB or SIFT) -> Lowe ratio matching -> RANSAC homography ->
perspective warp. Frames that cannot be aligned are returned unchanged and
flagged so the caller can drop or count them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

import cv2
import numpy as np

from app.logging_config import get_logger

KeyPoints = Sequence[cv2.KeyPoint]

logger = get_logger(__name__)

_LOWE_RATIO = 0.75
_MIN_MATCHES = 4  # findHomography needs 4 points; RANSAC filters the rest
_RANSAC_REPROJ = 5.0
_KNN_K = 2
_MIN_FRAMES = 2


@dataclass
class RegistrationResult:
    aligned: list[np.ndarray]
    homographies: list[np.ndarray]
    aligned_flags: list[bool]

    @property
    def success_rate(self) -> float:
        return sum(self.aligned_flags) / len(self.aligned_flags) if self.aligned_flags else 0.0


class RegistrationService:
    """Aligns a set of frames onto ``frames[reference_idx]``."""

    def __init__(self, detector: str = "orb") -> None:
        self.detector = detector.lower()

    def _make_detector(self) -> cv2.Feature2D:
        if self.detector == "sift":
            return cast("cv2.Feature2D", cv2.SIFT.create())
        return cast("cv2.Feature2D", cv2.ORB.create(nfeatures=5000))

    def _matcher(self) -> cv2.DescriptorMatcher:
        if self.detector == "sift":
            # FLANN_INDEX_KDTREE = 1
            index_params: dict[str, object] = {"algorithm": 1, "trees": 5}
            return cast(
                "cv2.DescriptorMatcher",
                cv2.FlannBasedMatcher(index_params, {"checks": 50}),  # type: ignore[arg-type]
            )
        return cast("cv2.DescriptorMatcher", cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False))

    def register(self, frames: list[np.ndarray], reference_idx: int = 0) -> RegistrationResult:
        if len(frames) < _MIN_FRAMES:
            return RegistrationResult(list(frames), [np.eye(3)] * len(frames), [True] * len(frames))

        reference = frames[reference_idx]
        height, width = reference.shape[:2]
        detector = self._make_detector()
        gray_ref = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY)
        kp_ref, desc_ref = detector.detectAndCompute(gray_ref, None)

        matcher = self._matcher()
        aligned: list[np.ndarray] = []
        homographies: list[np.ndarray] = []
        flags: list[bool] = []

        for index, frame in enumerate(frames):
            if index == reference_idx:
                aligned.append(frame)
                homographies.append(np.eye(3))
                flags.append(True)
                continue

            homography = self._homography(frame, detector, matcher, kp_ref, desc_ref)
            if homography is None:
                aligned.append(frame)
                homographies.append(np.eye(3))
                flags.append(False)
                logger.warning("frame not aligned", frame_index=index)
                continue

            warped = cv2.warpPerspective(frame, homography, (width, height))
            aligned.append(warped)
            homographies.append(homography)
            flags.append(True)

        return RegistrationResult(aligned, homographies, flags)

    def _homography(
        self,
        frame: np.ndarray,
        detector: cv2.Feature2D,
        matcher: cv2.DescriptorMatcher,
        kp_ref: KeyPoints,
        desc_ref: np.ndarray | None,
    ) -> np.ndarray | None:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        keypoints, descriptors = detector.detectAndCompute(gray, None)
        if descriptors is None or desc_ref is None or len(keypoints) < _MIN_MATCHES:
            return None

        good: list[cv2.DMatch] = []
        for pair in matcher.knnMatch(descriptors, desc_ref, _KNN_K):
            if len(pair) == _KNN_K and pair[0].distance < _LOWE_RATIO * pair[1].distance:
                good.append(pair[0])
        if len(good) < _MIN_MATCHES:
            return None

        src = np.array([keypoints[m.queryIdx].pt for m in good], dtype=np.float32).reshape(-1, 1, 2)
        dst = np.array([kp_ref[m.trainIdx].pt for m in good], dtype=np.float32).reshape(-1, 1, 2)
        homography, _mask = cv2.findHomography(src, dst, cv2.RANSAC, _RANSAC_REPROJ)
        return cast("np.ndarray | None", homography)
