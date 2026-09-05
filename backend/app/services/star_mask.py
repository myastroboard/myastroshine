"""StarMaskService - orchestrates the star-mask preview endpoint.

Runs detection against the session's full-resolution *original* image. This is
a close guide to, but not an exact match for, what `star_reduction` shrinks:
that pipeline stage runs after geometry (crop/rotate) and the tone stages, so
with a crop active or a strong tone curve the overlay positions and the
"N sources detected" count will drift from the final result.
An earlier version ran this against the downscaled preview image to stay
fast, back when detection used `skimage.feature.blob_dog`; now that detection
is a cheap top-hat + `cv2.connectedComponentsWithStats` pass (~140ms even at
24MP, see docs/ALGORITHMS.md), there's no accuracy/speed trade-off left to
make, and running on the downscaled copy was measurably under-detecting small
stars anyway. Mirrors :class:`DepthShiftService`'s session/storage/algorithm
split, minus the disk caching - this is a cheap, stateless, parameter-
dependent computation, not a discrete generated artifact.
"""

from __future__ import annotations

from app.logging_config import get_logger
from app.models import StarMaskResponse, StarSourceInfo
from app.services.session import SessionService
from app.services.star_detection import StarDetectionService
from app.services.storage import StorageService

logger = get_logger(__name__)


class StarMaskService:
    """Detects stars in a session's original image for the mask overlay."""

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
        image = self.storage.load_original(session_id)
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
