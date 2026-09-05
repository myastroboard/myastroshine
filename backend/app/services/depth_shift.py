"""DepthShiftService - orchestrates depth-map generation and layer caching.

Mirrors :class:`EnhancementService`: it ties the session lookup, the
:class:`DepthMapService` algorithms, and storage together for the routes.
"""

from __future__ import annotations

from pathlib import Path

from app.exceptions import ResourceNotFoundError
from app.logging_config import get_logger
from app.models import (
    DepthLayerInfo,
    DepthMetadataResponse,
    DepthShiftResponse,
    FocusPoint,
)
from app.services.depth_map import DepthMapService
from app.services.session import SessionService
from app.services.storage import StorageService

logger = get_logger(__name__)


class DepthShiftService:
    """Generates and serves the parallax depth artifacts for a session."""

    def __init__(
        self,
        sessions: SessionService,
        storage: StorageService,
        depth_maps: DepthMapService,
    ) -> None:
        self.sessions = sessions
        self.storage = storage
        self.depth_maps = depth_maps

    def _base_url(self, session_id: str) -> str:
        return f"/api/depth-shift/{session_id}"

    def generate(
        self, session_id: str, num_layers: int, focus_point: FocusPoint | None = None
    ) -> DepthShiftResponse:
        """Estimate depth, build parallax layers, and cache everything."""
        self.sessions.get_session(session_id)
        image = self.storage.load_processed(session_id)

        depth_map = self.depth_maps.estimate_depth(image, focus_point)
        layers = self.depth_maps.generate_parallax_layers(image, depth_map, num_layers)
        self.storage.save_depth(session_id, depth_map, layers)

        base = self._base_url(session_id)
        logger.info("depth shift generated", session_id=session_id, layers=num_layers)
        return DepthShiftResponse(
            session_id=session_id,
            num_layers=num_layers,
            depth_map_url=f"{base}/depth_map",
            depth_layers=[
                DepthLayerInfo(
                    layer_id=index,
                    depth_range=self.depth_maps.layer_depth_range(index, num_layers),
                    image_url=f"{base}/layer_{index}",
                )
                for index in range(num_layers)
            ],
            statistics=self.depth_maps.depth_statistics(depth_map),
        )

    def metadata(self, session_id: str) -> DepthMetadataResponse:
        """Report whether depth data exists and summarise it."""
        self.sessions.get_session(session_id)
        base = self._base_url(session_id)

        if not self.storage.has_depth(session_id):
            return DepthMetadataResponse(session_id=session_id, depth_map_generated=False)

        count = self.storage.count_layers(session_id)
        depth_map = self.storage.load_depth_map(session_id)
        return DepthMetadataResponse(
            session_id=session_id,
            depth_map_generated=True,
            statistics=self.depth_maps.depth_statistics(depth_map),
            layer_urls=[f"{base}/layer_{index}" for index in range(count)],
        )

    def layer_file(self, session_id: str, index: int) -> Path:
        self.sessions.get_session(session_id)
        path = self.storage.layer_path(session_id, index)
        if not path.exists():
            raise ResourceNotFoundError(f"Layer {index} not generated for {session_id}")
        return path

    def depth_map_file(self, session_id: str) -> Path:
        self.sessions.get_session(session_id)
        path = self.storage.depth_map_path(session_id)
        if not path.exists():
            raise ResourceNotFoundError(f"No depth map for {session_id}")
        return path
