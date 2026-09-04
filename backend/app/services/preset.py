"""PresetService - manage the built-in and user-created presets.

The five built-in presets are seeded on first read and cannot be deleted.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import PresetRecord
from app.exceptions import (
    DuplicateResourceError,
    ForbiddenError,
    PayloadTooLargeError,
    ResourceNotFoundError,
)
from app.logging_config import get_logger
from app.models import PresetOut, ProcessingParameters
from app.types import JsonDict

logger = get_logger(__name__)

MAX_USER_PRESETS = 50

# Built-in presets. Parameters left unset fall back to ProcessingParameters defaults.
_DEFAULTS: list[JsonDict] = [
    {
        "preset_id": "system_nebula",
        "name": "Nebula",
        "description": "Strong contrast and clarity for emission nebulae.",
        "parameters": {
            "contrast": 1.5,
            "clarity": 0.8,
            "saturation": 1.25,
            "vibrance": 1.2,
            "denoise": 20,
            "sharpness": 1.2,
            "temperature": 6200,
        },
    },
    {
        "preset_id": "system_galaxy",
        "name": "Galaxy",
        "description": "Balanced tone recovery for spiral and elliptical galaxies.",
        "parameters": {
            "contrast": 1.4,
            "clarity": 0.6,
            "saturation": 1.15,
            "shadows": 0.3,
            "denoise": 30,
            "sharpness": 1.15,
        },
    },
    {
        "preset_id": "system_deep_field",
        "name": "Deep Field",
        "description": "Aggressive shadow lift and noise reduction for faint wide fields.",
        "parameters": {
            "contrast": 1.6,
            "clarity": 0.5,
            "highlights": -0.2,
            "shadows": 0.4,
            "vibrance": 1.15,
            "denoise": 40,
            "sharpness": 1.1,
        },
    },
    {
        "preset_id": "system_lunar",
        "name": "Lunar",
        "description": "High micro-contrast and sharpness, muted colour for the Moon.",
        "parameters": {
            "contrast": 1.3,
            "clarity": 0.9,
            "saturation": 0.6,
            "denoise": 10,
            "sharpness": 1.5,
        },
    },
    {
        "preset_id": "system_cluster",
        "name": "Cluster",
        "description": "Crisp stars for open and globular clusters.",
        "parameters": {
            "contrast": 1.35,
            "clarity": 0.7,
            "saturation": 1.1,
            "denoise": 15,
            "sharpness": 1.4,
        },
    },
]


class PresetService:
    """CRUD for :class:`app.db.models.PresetRecord`."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def ensure_defaults(self) -> None:
        """Insert any missing built-in presets. Idempotent."""
        existing = set(self.db.scalars(select(PresetRecord.preset_id)).all())
        added = False
        for spec in _DEFAULTS:
            if spec["preset_id"] in existing:
                continue
            params = ProcessingParameters(**spec["parameters"])
            self.db.add(
                PresetRecord(
                    preset_id=spec["preset_id"],
                    name=spec["name"],
                    category="astronomy",
                    description=spec["description"],
                    parameters=params.model_dump(),
                    author="system",
                    is_favorite=False,
                )
            )
            added = True
        if added:
            self.db.commit()

    def list_presets(self) -> list[PresetOut]:
        """Return built-in presets first, then user presets by creation time."""
        self.ensure_defaults()
        records = self.db.scalars(
            select(PresetRecord).order_by(PresetRecord.author != "system", PresetRecord.created_at)
        ).all()
        return [self._to_out(record) for record in records]

    def get_preset(self, preset_id: str) -> PresetRecord:
        self.ensure_defaults()
        record = self.db.get(PresetRecord, preset_id)
        if record is None:
            raise ResourceNotFoundError(f"Preset {preset_id} not found")
        return record

    def save_preset(
        self,
        name: str,
        parameters: ProcessingParameters,
        description: str | None = None,
        category: str = "astronomy",
    ) -> PresetRecord:
        self.ensure_defaults()
        if self.db.scalar(select(PresetRecord).where(PresetRecord.name == name)) is not None:
            raise DuplicateResourceError(f"A preset named '{name}' already exists")

        user_count = self.db.scalar(
            select(func.count()).select_from(PresetRecord).where(PresetRecord.author == "user")
        )
        if (user_count or 0) >= MAX_USER_PRESETS:
            raise PayloadTooLargeError(f"Preset limit reached ({MAX_USER_PRESETS})")

        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "preset"
        record = PresetRecord(
            preset_id=f"user_{slug}_{uuid.uuid4().hex[:6]}",
            name=name,
            category=category,
            description=description,
            parameters=parameters.model_dump(),
            author="user",
            is_favorite=False,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        logger.info("preset saved", preset_id=record.preset_id)
        return record

    def delete_preset(self, preset_id: str) -> None:
        record = self.get_preset(preset_id)
        if record.author == "system":
            raise ForbiddenError("Built-in presets cannot be deleted")
        self.db.delete(record)
        self.db.commit()

    @staticmethod
    def _to_out(record: PresetRecord) -> PresetOut:
        return PresetOut(
            preset_id=record.preset_id,
            name=record.name,
            category=record.category,
            description=record.description,
            parameters=ProcessingParameters(**record.parameters),
            author=record.author,
            is_favorite=record.is_favorite,
        )
