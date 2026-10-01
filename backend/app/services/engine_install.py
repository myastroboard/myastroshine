"""EngineInstallService - install StarNet2 / DeepSNR from the archive the operator uploads.

MyAstroShine bundles no engine (THIRD_PARTY.md). The operator downloads the CLI
package from starnetastro.com and uploads it from Settings; this is the same as
copying their own licensed copy onto their own server, just without a shell.

Two steps, so the licence is read before anything is installed:

1. :meth:`EngineInstallService.stage` unpacks the archive into a staging
   directory under ``DATA_DIR/engines/``, checks it (the binary, its weights, its
   ``LICENSE.txt``, an ELF header for this machine's architecture) and runs the
   binary's ``--version``. It returns the package's licence text.
2. :meth:`EngineInstallService.install`, once the admin accepted that licence,
   swaps the package into ``DATA_DIR/engines/<engine>/`` atomically, points the
   ``<engine>_path`` setting at it and records the acceptance.

Unpacking is defensive: tar members go through Python's ``data`` extraction
filter (no absolute paths, no ``..``, no links leaving the tree, no device
files); zip members get the same rules by hand. Sizes and entry counts are
capped before anything is written. The engine files are never served back.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import stat
import tarfile
import time
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from app.config import get_settings
from app.constants import (
    DEEPSNR_TESTED_VERSIONS,
    ENGINE_ARCHIVE_MAX_ENTRIES,
    ENGINE_LICENSE_MAX_BYTES,
    ENGINE_STAGING_MAX_AGE_SECONDS,
    ENGINE_UNPACKED_MAX_BYTES,
    STARNET2_TESTED_VERSIONS,
)
from app.exceptions import InvalidEngineArchiveError, InvalidParameterError, ResourceNotFoundError
from app.logging_config import get_logger
from app.models.engines import EngineStatus
from app.services.engine_probe import clear_engine_probe_cache, probe_engine
from app.utils.app_settings import get_app_settings, save_app_settings

logger = get_logger(__name__)

_STAGING_PREFIX = ".staging-"
_OLD_PREFIX = ".old-"
_STAGING_META = "staging.json"
_INSTALLED_META = ".myastroshine-install.json"
_MAX_BINARY_DEPTH = 3
_COPY_CHUNK = 1024 * 1024

#: ELF ``e_machine`` per ``platform.machine()``.
_ELF_MACHINES = {"x86_64": 62, "amd64": 62, "aarch64": 183, "arm64": 183}
_ELF_MACHINE_NAMES = {62: "x86-64", 183: "arm64"}


@dataclass(frozen=True)
class EngineSpec:
    name: str  #: display name
    binary: str  #: the executable's file name inside the package
    tested: tuple[str, str]  #: the version range this app's CLI calls are tested with


ENGINES: dict[str, EngineSpec] = {
    "starnet2": EngineSpec("StarNet2", "starnet2", STARNET2_TESTED_VERSIONS),
    "deepsnr": EngineSpec("DeepSNR", "deepsnr", DEEPSNR_TESTED_VERSIONS),
}


@dataclass(frozen=True)
class StagedEngine:
    staging_id: str
    engine: str
    archive_name: str
    status: EngineStatus
    license_text: str


@dataclass(frozen=True)
class InstalledEngine:
    engine: str
    version: str | None
    archive_name: str
    license_accepted_at: str
    path: str


def host_elf_machine() -> int | None:
    """This machine's ELF ``e_machine``, or ``None`` for an architecture with no
    engine build."""
    return _ELF_MACHINES.get(platform.machine().lower())


def _spec(engine: str) -> EngineSpec:
    spec = ENGINES.get(engine)
    if spec is None:
        raise ResourceNotFoundError(f"Unknown engine {engine!r}")
    return spec


def _safe_member_path(name: str) -> PurePosixPath:
    """A relative, ``..``-free path for an archive member, or an error."""
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or (path.parts and ":" in path.parts[0]):
        raise InvalidEngineArchiveError(f"Unsafe path in the archive: {name}")
    return path


class EngineInstallService:
    """Stage, install and remove the operator's engine packages."""

    def __init__(self) -> None:
        self.root = get_settings().data_dir / "engines"

    # --- staging --------------------------------------------------------------

    def stage(self, engine: str, archive: BinaryIO, archive_name: str) -> StagedEngine:
        """Unpack and check an uploaded engine package (see the module docstring)."""
        spec = _spec(engine)
        staging_id = uuid.uuid4().hex
        staging = self.root / f"{_STAGING_PREFIX}{staging_id}"
        staging.mkdir(parents=True)
        try:
            self._unpack(archive, staging / "package")
            binary = self._find_binary(staging / "package", spec)
            self._check_package(binary, spec)
            binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            status = probe_engine(str(binary), spec.tested, name=spec.name)
            if not status.found:
                raise InvalidEngineArchiveError(
                    f"{spec.name} did not run on this server: {status.detail}"
                )
            license_text = (binary.parent / "LICENSE.txt").read_text(
                encoding="utf-8", errors="replace"
            )[:ENGINE_LICENSE_MAX_BYTES]
            (staging / _STAGING_META).write_text(
                json.dumps(
                    {
                        "engine": engine,
                        "archive_name": archive_name,
                        "package_dir": binary.parent.relative_to(staging).as_posix(),
                        "status": status.model_dump(),
                    }
                ),
                encoding="utf-8",
            )
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        logger.info(
            "engine package staged", engine=engine, version=status.version, archive=archive_name
        )
        return StagedEngine(staging_id, engine, archive_name, status, license_text)

    def _unpack(self, archive: BinaryIO, target: Path) -> None:
        target.mkdir()
        archive.seek(0)
        if zipfile.is_zipfile(archive):
            archive.seek(0)
            self._unpack_zip(archive, target)
            return
        archive.seek(0)
        try:
            with tarfile.open(fileobj=archive, mode="r:*") as tar:
                members = tar.getmembers()
                self._check_totals(len(members), sum(m.size for m in members if m.isfile()))
                tar.extractall(target, filter="data")
        except (tarfile.TarError, EOFError, OSError) as exc:
            raise InvalidEngineArchiveError(
                "Not a readable engine archive (expected .zip, .tar.gz or .tar.xz)"
            ) from exc

    @staticmethod
    def _check_totals(entries: int, unpacked_bytes: int) -> None:
        if entries > ENGINE_ARCHIVE_MAX_ENTRIES:
            raise InvalidEngineArchiveError(
                f"The archive has too many files (max {ENGINE_ARCHIVE_MAX_ENTRIES})"
            )
        if unpacked_bytes > ENGINE_UNPACKED_MAX_BYTES:
            raise InvalidEngineArchiveError(
                f"The archive unpacks to more than {ENGINE_UNPACKED_MAX_BYTES // 2**20} MiB"
            )

    def _unpack_zip(self, archive: BinaryIO, target: Path) -> None:
        with zipfile.ZipFile(archive) as zf:
            infos = zf.infolist()
            self._check_totals(len(infos), sum(info.file_size for info in infos))
            written = 0
            for info in infos:
                relative = _safe_member_path(info.filename)
                destination = target.joinpath(*relative.parts)
                mode = info.external_attr >> 16
                if info.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                if stat.S_ISLNK(mode):
                    link = zf.read(info).decode("utf-8")
                    resolved = (destination.parent / link).resolve()
                    if PurePosixPath(link).is_absolute() or not resolved.is_relative_to(
                        target.resolve()
                    ):
                        raise InvalidEngineArchiveError(
                            f"Link leaving the archive: {info.filename}"
                        )
                    os.symlink(link, destination)
                    continue
                # No file-type bits (Windows zippers, Python's writestr) means a plain file.
                if stat.S_IFMT(mode) and not stat.S_ISREG(mode):
                    raise InvalidEngineArchiveError(f"Special file in the archive: {info.filename}")
                with zf.open(info) as source, destination.open("wb") as sink:
                    while chunk := source.read(_COPY_CHUNK):
                        written += len(chunk)
                        if written > ENGINE_UNPACKED_MAX_BYTES:  # declared sizes can lie
                            raise InvalidEngineArchiveError(
                                "The archive unpacks to more than "
                                f"{ENGINE_UNPACKED_MAX_BYTES // 2**20} MiB"
                            )
                        sink.write(chunk)
                if mode & stat.S_IXUSR:
                    destination.chmod(destination.stat().st_mode | stat.S_IXUSR)

    @staticmethod
    def _find_binary(package: Path, spec: EngineSpec) -> Path:
        candidates = [
            path
            for path in package.rglob(spec.binary)
            if path.is_file()
            and not path.is_symlink()
            and len(path.relative_to(package).parts) <= _MAX_BINARY_DEPTH
        ]
        if len(candidates) != 1:
            raise InvalidEngineArchiveError(
                f"Expected one '{spec.binary}' executable in the archive, found "
                f"{len(candidates)} - is this the {spec.name} CLI package for Linux?"
            )
        return candidates[0]

    @staticmethod
    def _check_package(binary: Path, spec: EngineSpec) -> None:
        if not any(binary.parent.glob("*weights*.onnx")):
            raise InvalidEngineArchiveError(
                f"No {spec.name} model weights (*.onnx) next to the binary"
            )
        if not (binary.parent / "LICENSE.txt").is_file():
            raise InvalidEngineArchiveError(f"No LICENSE.txt next to the {spec.name} binary")
        with binary.open("rb") as handle:
            header = handle.read(20)
        if len(header) < 20 or header[:4] != b"\x7fELF":  # noqa: PLR2004 - ELF header size
            raise InvalidEngineArchiveError(f"'{spec.binary}' is not a Linux executable")
        machine = int.from_bytes(header[18:20], "little")
        host = host_elf_machine()
        if machine != host:
            built_for = _ELF_MACHINE_NAMES.get(machine, f"machine {machine}")
            raise InvalidEngineArchiveError(
                f"This {spec.name} build is for {built_for}; this server is "
                f"{platform.machine()}. starnetastro.com may not offer a build for it."
            )

    def discard(self, engine: str, staging_id: str) -> None:
        """Drop a staged package without installing it."""
        shutil.rmtree(self._staging_dir(engine, staging_id), ignore_errors=True)

    def _staging_dir(self, engine: str, staging_id: str) -> Path:
        _spec(engine)
        if not staging_id.isalnum():
            raise ResourceNotFoundError("Unknown staged engine package")
        staging = self.root / f"{_STAGING_PREFIX}{staging_id}"
        meta = staging / _STAGING_META
        if not meta.is_file() or json.loads(meta.read_text(encoding="utf-8"))["engine"] != engine:
            raise ResourceNotFoundError("Unknown or expired staged engine package")
        return staging

    def prune_stale_staging(self) -> int:
        """Delete staging (and leftover swap) directories older than
        ``ENGINE_STAGING_MAX_AGE_SECONDS``. Returns how many were removed."""
        if not self.root.is_dir():
            return 0
        cutoff = time.time() - ENGINE_STAGING_MAX_AGE_SECONDS
        removed = 0
        for entry in self.root.iterdir():
            stale = entry.name.startswith((_STAGING_PREFIX, _OLD_PREFIX))
            if stale and entry.is_dir() and entry.stat().st_mtime < cutoff:
                shutil.rmtree(entry, ignore_errors=True)
                removed += 1
        if removed:
            logger.info("stale engine staging removed", count=removed)
        return removed

    # --- install / remove -----------------------------------------------------

    def install(self, engine: str, staging_id: str, *, accept_license: bool) -> InstalledEngine:
        """Swap a staged package in, point the engine's path setting at it."""
        spec = _spec(engine)
        if not accept_license:
            raise InvalidParameterError(f"The {spec.name} licence must be accepted to install it")
        staging = self._staging_dir(engine, staging_id)
        meta = json.loads((staging / _STAGING_META).read_text(encoding="utf-8"))
        package = staging / meta["package_dir"]
        final = self.root / engine

        accepted_at = datetime.now(UTC).isoformat()
        status = EngineStatus.model_validate(meta["status"])
        (package / _INSTALLED_META).write_text(
            json.dumps(
                {
                    "version": status.version,
                    "archive_name": meta["archive_name"],
                    "license_accepted_at": accepted_at,
                }
            ),
            encoding="utf-8",
        )
        previous = None
        if final.exists():
            previous = self.root / f"{_OLD_PREFIX}{uuid.uuid4().hex}"
            final.rename(previous)
        package.rename(final)
        shutil.rmtree(staging, ignore_errors=True)
        if previous is not None:
            shutil.rmtree(previous, ignore_errors=True)

        binary = final / spec.binary
        save_app_settings({f"{engine}_path": str(binary)})  # also clears the probe cache
        logger.info("engine installed", engine=engine, version=status.version, path=str(binary))
        return InstalledEngine(
            engine, status.version, meta["archive_name"], accepted_at, str(binary)
        )

    def installed(self, engine: str) -> InstalledEngine | None:
        """The package installed from an upload, or ``None`` (none, or a manual path)."""
        spec = _spec(engine)
        final = self.root / engine
        meta_path = final / _INSTALLED_META
        if not meta_path.is_file():
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return InstalledEngine(
            engine,
            meta.get("version"),
            meta.get("archive_name", ""),
            meta.get("license_accepted_at", ""),
            str(final / spec.binary),
        )

    def remove(self, engine: str) -> None:
        """Delete the uploaded package; clear the path setting if it pointed into it."""
        _spec(engine)
        final = self.root / engine
        if not final.exists():
            raise ResourceNotFoundError(f"No uploaded {engine} package to remove")
        shutil.rmtree(final)
        current = getattr(get_app_settings(), f"{engine}_path")
        if current and Path(current).resolve().is_relative_to(final.resolve()):
            save_app_settings({f"{engine}_path": ""})
        clear_engine_probe_cache()
        logger.info("engine removed", engine=engine)
