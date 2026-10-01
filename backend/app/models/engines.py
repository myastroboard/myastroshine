"""External ML engine capability - the Settings panel's view of StarNet2 / DeepSNR.

See docs/DEPLOYMENT.md "External ML engines". These engines are never bundled; the
operator installs the binary and points a path at it (``starnet2_path`` /
``deepsnr_path`` in :class:`app.utils.app_settings.AppSettings`). This model is
what a ``--version`` probe of that path produced.
"""

from __future__ import annotations

from pydantic import BaseModel


class InstalledEngineOut(BaseModel):
    """A package installed by uploading it from Settings."""

    version: str | None = None
    archive_name: str
    license_accepted_at: str  #: ISO timestamp of the admin's licence acceptance
    path: str


class EngineStatus(BaseModel):
    """Result of probing one configured engine path."""

    configured: bool  #: a non-empty path is set for this engine
    found: bool  #: the path ran ``--version`` and looks like the right tool
    version: str | None = None  #: parsed "x.y.z" from ``--version``, when readable
    known_good: bool = False  #: version is inside the range this app was tested against
    detail: str  #: one line for the Settings panel and the logs
    #: Set by ``GET /api/admin/engine-status`` when the package was uploaded from
    #: Settings (``None``: nothing uploaded - a manual path, or no engine).
    installed: InstalledEngineOut | None = None


class StagedEngineResponse(BaseModel):
    """Body of ``POST /api/admin/engines/{engine}/stage``: the unpacked, checked
    package waiting for the licence to be accepted."""

    staging_id: str
    engine: str
    archive_name: str
    status: EngineStatus
    license_text: str


class InstallEngineRequest(BaseModel):
    """Body of ``POST /api/admin/engines/{engine}/install``."""

    staging_id: str
    #: The admin read the package's LICENSE.txt and accepts it.
    accept_license: bool = False


class EngineStatusResponse(BaseModel):
    """Body of ``GET /api/admin/engine-status``."""

    starnet2: EngineStatus
    deepsnr: EngineStatus
