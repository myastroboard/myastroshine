"""External ML engine packages, uploaded from Settings.

POST   /api/admin/engines/{engine}/stage                 - unpack + check an uploaded package
POST   /api/admin/engines/{engine}/install               - accept its licence and install it
DELETE /api/admin/engines/{engine}/stage/{staging_id}    - drop a staged package
DELETE /api/admin/engines/{engine}                       - remove the installed package

``engine`` is ``starnet2`` or ``deepsnr``. Admin only: installing an engine
means running a binary on this server. See ``app.services.engine_install``.
"""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app.constants import ENGINE_ARCHIVE_MAX_BYTES
from app.dependencies import RequireAdmin, RequireRateLimit
from app.exceptions import PayloadTooLargeError
from app.models import EngineStatus, InstalledEngineOut, InstallEngineRequest, StagedEngineResponse
from app.services.engine_install import EngineInstallService
from app.services.engine_probe import get_engine_statuses

router = APIRouter(prefix="/admin/engines", tags=["admin"])


@router.post(
    "/{engine}/stage", status_code=status.HTTP_201_CREATED, response_model=StagedEngineResponse
)
async def stage_engine(
    engine: str,
    _admin: RequireAdmin,
    _rate_limit: RequireRateLimit,
    file: UploadFile = File(...),
) -> StagedEngineResponse:
    """Unpack and check the uploaded package; answer with its licence text."""
    if file.size is not None and file.size > ENGINE_ARCHIVE_MAX_BYTES:
        raise PayloadTooLargeError(
            f"Engine archive exceeds {ENGINE_ARCHIVE_MAX_BYTES // 2**20} MiB"
        )
    staged = await run_in_threadpool(
        EngineInstallService().stage, engine, file.file, file.filename or "archive"
    )
    return StagedEngineResponse(
        staging_id=staged.staging_id,
        engine=staged.engine,
        archive_name=staged.archive_name,
        status=staged.status,
        license_text=staged.license_text,
    )


@router.post("/{engine}/install", response_model=EngineStatus)
async def install_engine(
    engine: str,
    body: InstallEngineRequest,
    _admin: RequireAdmin,
    _rate_limit: RequireRateLimit,
) -> EngineStatus:
    """Install a staged package once its licence is accepted; answer with the
    engine's fresh status."""
    service = EngineInstallService()
    installed = await run_in_threadpool(
        service.install, engine, body.staging_id, accept_license=body.accept_license
    )
    probed = (await run_in_threadpool(get_engine_statuses))[engine]
    return probed.model_copy(
        update={"installed": InstalledEngineOut.model_validate(installed, from_attributes=True)}
    )


@router.delete("/{engine}/stage/{staging_id}", status_code=status.HTTP_204_NO_CONTENT)
async def discard_staged_engine(
    engine: str, staging_id: str, _admin: RequireAdmin, _rate_limit: RequireRateLimit
) -> None:
    """Drop a staged package (the admin declined the licence or cancelled)."""
    await run_in_threadpool(EngineInstallService().discard, engine, staging_id)


@router.delete("/{engine}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_engine(engine: str, _admin: RequireAdmin, _rate_limit: RequireRateLimit) -> None:
    """Delete the uploaded package (and clear the path setting pointing into it)."""
    await run_in_threadpool(EngineInstallService().remove, engine)
