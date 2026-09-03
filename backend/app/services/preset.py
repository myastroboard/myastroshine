"""PresetService - manage system and user presets.

System defaults: Nebula, Galaxy, Deep Field, Lunar, Cluster.
"""

from __future__ import annotations

from app.logging_config import get_logger
from app.models import ProcessingParameters
from app.types import JsonDict

logger = get_logger(__name__)

DEFAULT_PRESET_NAMES = ("Nebula", "Galaxy", "Deep Field", "Lunar", "Cluster")


class PresetService:
    """CRUD for :class:`app.db.models.PresetRecord`."""

    def list_presets(self) -> list[JsonDict]:
        """Return system defaults followed by user presets."""
        raise NotImplementedError

    def save_preset(
        self, name: str, parameters: ProcessingParameters, description: str | None = None
    ) -> JsonDict:
        """Create a user preset (max 50 per instance)."""
        raise NotImplementedError

    def get_preset(self, preset_id: str) -> JsonDict:
        """Load a preset by id or raise if missing."""
        raise NotImplementedError

    def delete_preset(self, preset_id: str) -> None:
        """Delete a user preset (system presets cannot be deleted)."""
        raise NotImplementedError

    def seed_defaults(self) -> None:
        """Insert the built-in presets if they are not present yet."""
        raise NotImplementedError
