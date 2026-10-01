"""EngineInstallService: staging an uploaded engine package, installing it, removing it."""

from __future__ import annotations

import io
import json
import os
import stat
import tarfile
import time
import zipfile
from pathlib import Path

import pytest

from app.config import get_settings
from app.exceptions import InvalidEngineArchiveError, InvalidParameterError, ResourceNotFoundError
from app.models.engines import EngineStatus
from app.services import engine_install
from app.services.engine_install import EngineInstallService
from app.utils.app_settings import get_app_settings, save_app_settings

#: The real function, captured before the autouse fixture stubs it.
REAL_HOST_ELF_MACHINE = engine_install.host_elf_machine

X86_64 = 62
ARM64 = 183
LICENSE = "STARNET2 SOFTWARE LICENSE AGREEMENT\nUse solely for astrophotography."


def elf(machine: int = X86_64) -> bytes:
    """The first bytes of a 64-bit little-endian ELF executable for ``machine``."""
    return (
        b"\x7fELF\x02\x01\x01"
        + b"\0" * 9
        + (2).to_bytes(2, "little")
        + machine.to_bytes(2, "little")
        + b"\0" * 44
    )


def package_files(binary: str = "starnet2", root: str = "StarNet2_CLI") -> dict[str, bytes]:
    prefix = f"{root}/" if root else ""
    return {
        f"{prefix}{binary}": elf(),
        f"{prefix}StarNet2_weights.onnx": b"weights",
        f"{prefix}LICENSE.txt": LICENSE.encode(),
        f"{prefix}lib/libonnxruntime.so.1": b"lib",
    }


def zip_archive(files: dict[str, bytes], links: dict[str, str] | None = None) -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFREG | 0o755) << 16
            archive.writestr(info, data)
        for name, target in (links or {}).items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, target)
    buffer.seek(0)
    return buffer


def tar_archive(files: dict[str, bytes], links: dict[str, str] | None = None) -> io.BytesIO:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755
            archive.addfile(info, io.BytesIO(data))
        for name, target in (links or {}).items():
            info = tarfile.TarInfo(name)
            info.type = tarfile.SYMTYPE
            info.linkname = target
            archive.addfile(info)
    buffer.seek(0)
    return buffer


LIB_LINK = {"StarNet2_CLI/lib/libonnxruntime.so": "libonnxruntime.so.1"}


@pytest.fixture(autouse=True)
def _fake_host_and_probe(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """An x86-64 host whose engine probe succeeds, recording what it ran."""
    probed: list[str] = []

    def probe(path: str, tested: tuple[str, str], *, name: str) -> EngineStatus:
        probed.append(path)
        return EngineStatus(
            configured=True, found=True, version="2.6.1", known_good=True, detail=f"{name} 2.6.1"
        )

    monkeypatch.setattr(engine_install, "host_elf_machine", lambda: X86_64)
    monkeypatch.setattr(engine_install, "probe_engine", probe)
    return probed


@pytest.fixture
def service() -> EngineInstallService:
    return EngineInstallService()


def engines_root() -> Path:
    return get_settings().data_dir / "engines"


# --- staging ------------------------------------------------------------------


@pytest.mark.parametrize("make", [zip_archive, tar_archive])
def test_stage_unpacks_checks_and_returns_the_licence(
    service: EngineInstallService, make, _fake_host_and_probe: list[str]
) -> None:
    """A zip or a tar.gz of the CLI package stages, keeping its lib/ links."""
    staged = service.stage("starnet2", make(package_files(), LIB_LINK), "starnet2-linux.zip")

    assert staged.license_text == LICENSE
    assert staged.status.version == "2.6.1"
    staging = engines_root() / f".staging-{staged.staging_id}"
    binary = staging / "package" / "StarNet2_CLI" / "starnet2"
    assert _fake_host_and_probe == [str(binary)]
    if os.name != "nt":
        assert binary.stat().st_mode & stat.S_IXUSR
    link = binary.parent / "lib" / "libonnxruntime.so"
    assert link.is_symlink()
    assert link.resolve().name == "libonnxruntime.so.1"


def test_stage_accepts_a_package_without_a_top_folder(service: EngineInstallService) -> None:
    staged = service.stage("starnet2", zip_archive(package_files(root="")), "flat.zip")

    assert staged.engine == "starnet2"


def test_stage_handles_directory_entries_and_plain_files_in_a_zip(
    service: EngineInstallService,
) -> None:
    """Real zips list their folders, and not every file is executable."""
    buffer = zip_archive(package_files())
    with zipfile.ZipFile(buffer, "a") as archive:
        archive.writestr(zipfile.ZipInfo("StarNet2_CLI/docs/"), b"")
        archive.writestr(zipfile.ZipInfo("StarNet2_CLI/docs/README.txt"), b"read me")
    buffer.seek(0)

    staged = service.stage("starnet2", buffer, "starnet2.zip")

    package = engines_root() / f".staging-{staged.staging_id}" / "package" / "StarNet2_CLI"
    assert (package / "docs" / "README.txt").read_text() == "read me"


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ({k: v for k, v in package_files().items() if "weights" not in k}, "weights"),
        ({k: v for k, v in package_files().items() if "LICENSE" not in k}, "LICENSE"),
        (package_files(binary="deepsnr"), "Expected one 'starnet2'"),
        ({**package_files(), "StarNet2_CLI/starnet2": b"#!/bin/sh\necho hi"}, "not a Linux"),
        ({**package_files(), "StarNet2_CLI/starnet2": elf(ARM64)}, "arm64"),
        ({**package_files(), "other/starnet2": elf()}, "found 2"),
    ],
)
def test_stage_refuses_a_package_that_is_not_the_expected_tool(
    service: EngineInstallService, files: dict[str, bytes], message: str
) -> None:
    with pytest.raises(InvalidEngineArchiveError, match=message):
        service.stage("starnet2", zip_archive(files), "bad.zip")

    assert not any(engines_root().glob(".staging-*"))  # nothing left behind


def test_stage_refuses_a_build_for_another_architecture_on_arm(
    service: EngineInstallService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real case: the x86-64 package on a Raspberry Pi."""
    monkeypatch.setattr(engine_install, "host_elf_machine", lambda: ARM64)

    with pytest.raises(InvalidEngineArchiveError, match="x86-64"):
        service.stage("starnet2", zip_archive(package_files()), "starnet2.zip")


def test_stage_refuses_a_binary_that_does_not_run(
    service: EngineInstallService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        engine_install,
        "probe_engine",
        lambda *_a, **_k: EngineStatus(configured=True, found=False, detail="exit 127"),
    )

    with pytest.raises(InvalidEngineArchiveError, match=r"did not run.*exit 127"):
        service.stage("starnet2", zip_archive(package_files()), "starnet2.zip")


@pytest.mark.parametrize("name", ["../evil", "/etc/evil", "StarNet2_CLI/../../evil", "C:/evil"])
def test_stage_refuses_a_zip_path_leaving_the_package(
    service: EngineInstallService, name: str
) -> None:
    with pytest.raises(InvalidEngineArchiveError, match="Unsafe path"):
        service.stage("starnet2", zip_archive({**package_files(), name: b"x"}), "evil.zip")


def test_stage_refuses_links_leaving_the_package(service: EngineInstallService) -> None:
    with pytest.raises(InvalidEngineArchiveError, match="Link leaving"):
        service.stage(
            "starnet2",
            zip_archive(package_files(), {"StarNet2_CLI/lib/x.so": "../../../../etc/passwd"}),
            "evil.zip",
        )
    with pytest.raises(InvalidEngineArchiveError):  # the tar "data" filter refuses it too
        service.stage(
            "starnet2",
            tar_archive(package_files(), {"StarNet2_CLI/lib/x.so": "/etc/passwd"}),
            "evil.tar.gz",
        )


def test_stage_refuses_special_files_in_a_zip(service: EngineInstallService) -> None:
    buffer = zip_archive(package_files())
    with zipfile.ZipFile(buffer, "a") as archive:
        info = zipfile.ZipInfo("StarNet2_CLI/fifo")
        info.external_attr = (stat.S_IFIFO | 0o644) << 16
        archive.writestr(info, b"")
    buffer.seek(0)

    with pytest.raises(InvalidEngineArchiveError, match="Special file"):
        service.stage("starnet2", buffer, "evil.zip")


def test_stage_refuses_archives_over_the_size_or_entry_caps(
    service: EngineInstallService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(engine_install, "ENGINE_ARCHIVE_MAX_ENTRIES", 3)
    with pytest.raises(InvalidEngineArchiveError, match="too many files"):
        service.stage("starnet2", zip_archive(package_files()), "big.zip")

    monkeypatch.setattr(engine_install, "ENGINE_ARCHIVE_MAX_ENTRIES", 5000)
    monkeypatch.setattr(engine_install, "ENGINE_UNPACKED_MAX_BYTES", 10)
    with pytest.raises(InvalidEngineArchiveError, match="unpacks to more"):
        service.stage("starnet2", tar_archive(package_files()), "big.tar.gz")


def test_stage_stops_a_zip_member_that_lies_about_its_size(
    service: EngineInstallService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The declared sizes pass the cap, the bytes actually written do not."""
    monkeypatch.setattr(engine_install, "ENGINE_UNPACKED_MAX_BYTES", 100)
    monkeypatch.setattr(EngineInstallService, "_check_totals", staticmethod(lambda *_a: None))

    with pytest.raises(InvalidEngineArchiveError, match="unpacks to more"):
        service.stage("starnet2", zip_archive(package_files()), "lying.zip")


def test_stage_refuses_something_that_is_not_an_archive(service: EngineInstallService) -> None:
    with pytest.raises(InvalidEngineArchiveError, match="Not a readable engine archive"):
        service.stage("starnet2", io.BytesIO(b"definitely not an archive"), "x.bin")


def test_stage_refuses_an_unknown_engine(service: EngineInstallService) -> None:
    with pytest.raises(ResourceNotFoundError):
        service.stage("photoshop", zip_archive(package_files()), "x.zip")


# --- install ------------------------------------------------------------------


def test_install_swaps_the_package_in_and_points_the_setting_at_it(
    service: EngineInstallService,
) -> None:
    staged = service.stage("starnet2", zip_archive(package_files(), LIB_LINK), "starnet2.zip")

    installed = service.install("starnet2", staged.staging_id, accept_license=True)

    binary = engines_root() / "starnet2" / "starnet2"
    assert installed.path == str(binary)
    assert binary.is_file()
    assert get_app_settings().starnet2_path == str(binary)
    assert not any(engines_root().glob(".staging-*"))
    recorded = service.installed("starnet2")
    assert recorded is not None
    assert (recorded.version, recorded.archive_name) == ("2.6.1", "starnet2.zip")
    assert recorded.license_accepted_at


def test_install_replaces_a_previous_package(service: EngineInstallService) -> None:
    first = service.stage("starnet2", zip_archive(package_files()), "old.zip")
    service.install("starnet2", first.staging_id, accept_license=True)
    second = service.stage("starnet2", tar_archive(package_files()), "new.tar.gz")

    service.install("starnet2", second.staging_id, accept_license=True)

    assert service.installed("starnet2").archive_name == "new.tar.gz"  # type: ignore[union-attr]
    assert not any(engines_root().glob(".old-*"))


def test_install_needs_the_licence_accepted(service: EngineInstallService) -> None:
    staged = service.stage("starnet2", zip_archive(package_files()), "starnet2.zip")

    with pytest.raises(InvalidParameterError, match="licence"):
        service.install("starnet2", staged.staging_id, accept_license=False)

    assert get_app_settings().starnet2_path == ""


@pytest.mark.parametrize("staging_id", ["0123abcd", "../../etc", ""])
def test_install_refuses_an_unknown_staging_id(
    service: EngineInstallService, staging_id: str
) -> None:
    with pytest.raises(ResourceNotFoundError):
        service.install("starnet2", staging_id, accept_license=True)


def test_install_refuses_a_package_staged_for_the_other_engine(
    service: EngineInstallService,
) -> None:
    staged = service.stage("starnet2", zip_archive(package_files()), "starnet2.zip")

    with pytest.raises(ResourceNotFoundError):
        service.install("deepsnr", staged.staging_id, accept_license=True)


def test_installed_is_none_without_an_uploaded_package(service: EngineInstallService) -> None:
    assert service.installed("deepsnr") is None


# --- discard, prune, remove ---------------------------------------------------


def test_discard_drops_a_staged_package(service: EngineInstallService) -> None:
    staged = service.stage("starnet2", zip_archive(package_files()), "starnet2.zip")

    service.discard("starnet2", staged.staging_id)

    assert not any(engines_root().glob(".staging-*"))


def test_prune_removes_only_stale_staging(service: EngineInstallService) -> None:
    fresh = service.stage("starnet2", zip_archive(package_files()), "fresh.zip")
    stale = service.stage("starnet2", zip_archive(package_files()), "stale.zip")
    old = time.time() - 2 * 3600
    os.utime(engines_root() / f".staging-{stale.staging_id}", (old, old))

    assert service.prune_stale_staging() == 1
    assert (engines_root() / f".staging-{fresh.staging_id}").is_dir()
    assert service.prune_stale_staging() == 0


def test_prune_is_a_no_op_before_any_engine_upload(service: EngineInstallService) -> None:
    assert service.prune_stale_staging() == 0


def test_remove_deletes_the_package_and_clears_its_path(service: EngineInstallService) -> None:
    staged = service.stage("starnet2", zip_archive(package_files()), "starnet2.zip")
    service.install("starnet2", staged.staging_id, accept_license=True)

    service.remove("starnet2")

    assert not (engines_root() / "starnet2").exists()
    assert get_app_settings().starnet2_path == ""


def test_remove_keeps_a_manual_path_pointing_elsewhere(service: EngineInstallService) -> None:
    staged = service.stage("starnet2", zip_archive(package_files()), "starnet2.zip")
    service.install("starnet2", staged.staging_id, accept_license=True)
    save_app_settings({"starnet2_path": "/opt/engines/starnet2/starnet2"})

    service.remove("starnet2")

    assert get_app_settings().starnet2_path == "/opt/engines/starnet2/starnet2"


def test_remove_without_an_uploaded_package_is_not_found(service: EngineInstallService) -> None:
    with pytest.raises(ResourceNotFoundError):
        service.remove("deepsnr")


def test_staging_metadata_is_never_shared_between_engines(service: EngineInstallService) -> None:
    staged = service.stage("starnet2", zip_archive(package_files()), "starnet2.zip")
    meta = json.loads(
        (engines_root() / f".staging-{staged.staging_id}" / "staging.json").read_text()
    )

    assert meta["engine"] == "starnet2"


def test_host_elf_machine_maps_the_common_architectures(monkeypatch: pytest.MonkeyPatch) -> None:
    for machine, expected in [("x86_64", 62), ("AMD64", 62), ("aarch64", 183), ("riscv64", None)]:
        monkeypatch.setattr(engine_install.platform, "machine", lambda m=machine: m)
        assert REAL_HOST_ELF_MACHINE() == expected
