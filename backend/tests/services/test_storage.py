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


def test_linear_frame_is_stored_compact_and_round_trips(tmp_path: Path) -> None:
    """A 16-bit source frame is stored as uint16 (half the size of float32) and
    reloads bit-exactly; a float source keeps float32."""
    from app.utils.linear_ingest import LinearFrame

    storage = StorageService(root=tmp_path)
    rng = np.random.default_rng(3)
    data = rng.random((64, 96), dtype=np.float32)

    storage.save_linear_frame("s", 0, LinearFrame(data=data, source_bit_depth=16))
    stored = np.load(storage.linear_frame_path("s", 0))
    assert stored.dtype == np.uint16
    back = storage.load_linear_frame("s", 0)
    assert back.data.dtype == np.float32
    np.testing.assert_allclose(back.data, data, atol=1.0 / 65535)

    storage.save_linear_frame("s", 1, LinearFrame(data=data, source_bit_depth=32))
    assert np.load(storage.linear_frame_path("s", 1)).dtype == np.float32


def test_stack_sky_mask_round_trips_and_is_optional(tmp_path: Path) -> None:
    """A nightscape composite's sky mask is stored next to it; a stack without one
    loads ``None``."""
    storage = StorageService(root=tmp_path)
    assert storage.load_stack_sky_mask("stack-1") is None

    mask = np.zeros((6, 8), dtype=np.uint8)
    mask[:4] = 255
    storage.save_stack_sky_mask("stack-1", mask)
    loaded = storage.load_stack_sky_mask("stack-1")
    assert loaded is not None
    assert np.array_equal(loaded, mask)


def test_stack_render_hints_round_trip_and_are_optional(tmp_path: Path) -> None:
    """The render hints sidecar is stored next to the composite; absent -> None."""
    storage = StorageService(root=tmp_path)
    assert storage.load_stack_render_hints("stack-1") is None
    storage.save_stack_render_hints("stack-1", {"camera_processed": True, "wide_field": False})
    assert storage.load_stack_render_hints("stack-1") == {
        "camera_processed": True,
        "wide_field": False,
    }


def test_prelook_round_trips_and_checks_its_key(tmp_path: Path) -> None:
    """The pre-look render is stored losslessly with a thumbnail, and a stale key misses."""
    storage = StorageService(tmp_path)
    image = np.random.default_rng(1).integers(0, 255, (900, 1200, 3), dtype=np.uint8)
    assert storage.load_prelook("s1") is None
    assert storage.load_prelook_thumb("s1") is None

    storage.save_prelook("s1", image, "key-a")

    assert np.array_equal(storage.load_prelook("s1"), image)
    assert np.array_equal(storage.load_prelook("s1", "key-a"), image)
    assert storage.load_prelook("s1", "key-b") is None
    thumb = storage.load_prelook_thumb("s1")
    assert thumb is not None
    assert max(thumb.shape[:2]) == 400


def test_prelook_without_its_key_file_is_a_cache_miss(tmp_path: Path) -> None:
    """A pre-look image whose key file is missing is never trusted as a cache hit."""
    storage = StorageService(tmp_path)
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    storage.save_prelook("s1", image, "key-a")
    (storage.session_dir("s1") / "prelook.json").unlink()
    assert storage.load_prelook("s1", "key-a") is None
    assert storage.load_prelook("s1") is not None
