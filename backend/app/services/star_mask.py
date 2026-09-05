"""StarMaskService - orchestrates the star-mask preview endpoint.

Runs detection against a session's cached *preview* image (not the full
original), so the mask preview stays fast on every toggle/slider change,
independent of the full-resolution enhancement pipeline's own cost. Mirrors
:class:`DepthShiftService`'s session/storage/algorithm split, minus the disk
caching - this is a cheap, stateless, parameter-dependent computation, not a
discrete generated artifact.
"""

from __future__ import annotations

from app.logging_config import get_logger
from app.models import StarMaskResponse, StarSourceInfo
from app.services.session import SessionService
from app.services.star_detection import StarDetectionService
from app.services.storage import StorageService

logger = get_logger(__name__)


class StarMaskService:
    """Detects stars in a session's preview image for the mask overlay."""

    def __init__(
        self,
        sessions: SessionService,
        storage: StorageService,
        detector: StarDetectionService,
    ) -> None:
        self.sessions = sessions
        self.storage = storage
        self.detector = detector

    def preview(self, session_id: str, sensitivity: int, max_size: int) -> StarMaskResponse:
        """Detect stars and report their positions as fractions of the image size."""
        self.sessions.get_session(session_id)
        image = self.storage.load_preview(session_id)
        height, width = image.shape[:2]
        longest_side = max(width, height)

        stars = self.detector.detect(image, sensitivity, max_size)
        logger.info("star mask detected", session_id=session_id, count=len(stars))
        return StarMaskResponse(
            session_id=session_id,
            source_count=len(stars),
            stars=[
                StarSourceInfo(
                    x=min(1.0, star.x / width),
                    y=min(1.0, star.y / height),
                    radius=min(1.0, star.radius / longest_side),
                )
                for star in stars
            ],
        )
