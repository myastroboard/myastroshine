"""Disk-usage reporting for the health check and the admin Settings panel."""

from __future__ import annotations

from app.config import get_settings
from app.utils.disk_usage import _dir_size, data_breakdown, volume_usage


def test_volume_usage_reports_filesystem_totals() -> None:
    usage = volume_usage()
    assert usage["total_bytes"] > 0
    assert usage["used_bytes"] >= 0
    assert usage["free_bytes"] >= 0


def test_dir_size_of_a_nonexistent_path_is_zero() -> None:
    settings = get_settings()
    assert _dir_size(settings.data_dir / "does-not-exist") == 0


def test_dir_size_sums_file_bytes_recursively() -> None:
    settings = get_settings()
    target = settings.data_dir / "some_dir"
    (target / "nested").mkdir(parents=True)
    (target / "a.txt").write_bytes(b"12345")
    (target / "nested" / "b.txt").write_bytes(b"1234567890")

    assert _dir_size(target) == 15


def test_dir_size_excludes_the_given_subtree() -> None:
    settings = get_settings()
    target = settings.data_dir / "with_exclude"
    excluded = target / "excluded"
    excluded.mkdir(parents=True)
    (target / "kept.txt").write_bytes(b"1234")
    (excluded / "skipped.txt").write_bytes(b"567890")

    assert _dir_size(target, exclude=excluded) == 4


def test_data_breakdown_reports_each_bucket() -> None:
    settings = get_settings()
    settings.ensure_data_dirs()
    (settings.images_dir / "photo.jpg").write_bytes(b"12345")
    stacks_dir = settings.images_dir / "stacks"
    stacks_dir.mkdir(parents=True, exist_ok=True)
    (stacks_dir / "stack.fit").write_bytes(b"1234567890")
    settings.log_file.write_text("log line", encoding="utf-8")

    breakdown = data_breakdown()

    assert breakdown["images_bytes"] == 5  # stacks/ is excluded from images
    assert breakdown["stacks_bytes"] == 10
    assert breakdown["logs_bytes"] >= len(b"log line")
    assert breakdown["db_bytes"] >= 0
