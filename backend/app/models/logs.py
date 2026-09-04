"""Admin log endpoint models."""

from __future__ import annotations

from pydantic import BaseModel, field_validator

from app.constants import LOG_LEVELS


class LogLevels(BaseModel):
    """The two independently controlled sink levels."""

    file: str
    console: str


class LogLevelUpdate(BaseModel):
    """Body of ``POST /api/admin/logs/level`` - either field may be omitted."""

    file: str | None = None
    console: str | None = None

    @field_validator("file", "console", mode="after")
    @classmethod
    def _known_level(cls, value: str | None) -> str | None:
        if value is not None and value.lower() not in LOG_LEVELS:
            raise ValueError(f"level must be one of {', '.join(LOG_LEVELS)}")
        return value.lower() if value is not None else None


class LogTailResponse(BaseModel):
    """Body of ``GET /api/admin/logs`` - newest line first."""

    lines: list[str]
    returned: int
    filtered_level: str | None = None
