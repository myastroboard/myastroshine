"""StorageService filesystem layout and IO."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from app.services.storage import StorageService


def test_save_original_creates_all_three_files(tmp_path: Path, sample_image: np.ndarray) -> None:
    """Upload writes original + processed + preview under the session directory."""
    storage = StorageService(root=tmp_path)
    storage.save_original("sess-1", sample_image)

    assert storage.original_path("sess-1").exists()
    assert storage.processed_path("sess-1").exists()
    assert storage.preview_path("sess-1").exists()
    assert storage.has_session("sess-1")


def test_save_result_updates_processed_and_preview(
    tmp_path: Path, sample_image: np.ndarray
) -> None:
    """A new result overwrites processed.jpg and regenerates the preview."""
    storage = StorageService(root=tmp_path)
    storage.save_original("sess-2", sample_image)
    brighter = np.clip(sample_image.astype(int) + 40, 0, 255).astype(np.uint8)
    storage.save_result("sess-2", brighter)

    reloaded = storage.load_processed("sess-2")
    assert reloaded.mean() > storage.load_original("sess-2").mean()


def test_delete_session_removes_directory(tmp_path: Path, sample_image: np.ndarray) -> None:
    """delete_session clears the whole working directory."""
    storage = StorageService(root=tmp_path)
    storage.save_original("sess-3", sample_image)
    storage.delete_session("sess-3")

    assert not storage.has_session("sess-3")
    assert not storage.session_dir("sess-3", create=False).exists()


def test_preview_is_downscaled_processed_is_full_res(tmp_path: Path) -> None:
    """A large image keeps full resolution in processed.jpg but a small preview."""
    from app.utils import image_utils

    storage = StorageService(root=tmp_path)
    big = np.full((1200, 1600, 3), 128, dtype=np.uint8)
    storage.save_original("sess-4", big)

    preview_img = image_utils.load_image(storage.preview_path("sess-4"))
    assert max(preview_img.shape[:2]) <= 512
    assert storage.load_processed("sess-4").shape[0] == 1200
