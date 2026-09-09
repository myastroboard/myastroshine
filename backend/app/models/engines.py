"""External ML engine capability - the Settings panel's view of StarNet2 / DeepSNR.

See initial_plan/13_EXTERNAL_ML_ENGINES.md. These engines are never bundled; the
operator installs the binary and points a path at it (``starnet2_path`` /
``deepsnr_path`` in :class:`app.utils.app_settings.AppSettings`). This model is
what a ``--version`` probe of that path produced.
"""

from __future__ import annotations

from pydantic import BaseModel


class EngineStatus(BaseModel):
    """Result of probing one configured engine path."""

    configured: bool  #: a non-empty path is set for this engine
    found: bool  #: the path ran ``--version`` and looks like the right tool
    version: str | None = None  #: parsed "x.y.z" from ``--version``, when readable
    known_good: bool = False  #: version is inside the range this app was tested against
    detail: str  #: one line for the Settings panel and the logs


class EngineStatusResponse(BaseModel):
    """Body of ``GET /api/admin/engine-status``."""

    starnet2: EngineStatus
    deepsnr: EngineStatus
