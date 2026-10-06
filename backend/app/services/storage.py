"""StorageService - filesystem layout and IO for session working files.

Layout (per docs/ARCHITECTURE):
    {DATA_DIR}/images/{session_id}/
        original.jpg      full-resolution upload
        processed.jpg     full-resolution latest result
        preview.jpg       downscaled processed image (fast display)
        prelook.npy       lossless full-res result *before* the "Style" look
        prelook.json      {"key": ...} - the edit that produced prelook.npy
        prelook_thumb.png downscaled prelook, the Style gallery's source
        depth/depth_map.png
        depth/layer_{n}.png    BGRA parallax layers, far (0) to near
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from app.config import get_settings
from app.logging_config import get_logger
from app.utils import image_utils
from app.utils.app_settings import get_app_settings
from app.utils.linear_ingest import LinearFrame, to_display_bgr

logger = get_logger(__name__)

_STACK_THUMB_MAX_SIZE = 256
_FRAME_INDEX_WIDTH = 5  # frames/00000.npy .. supports 99999 frames
_CALIBRATION_KINDS = ("dark", "flat", "bias", "dark_flat")
#: Stack frames are stored at their source bit depth, not float32 - a 16-bit
#: camera frame round-trips through uint16 losslessly at half the size (an
#: uncompressed float32 .npy of a 2 MP CFA frame is 8 MB; uint16 is 4 MB). A
#: float FITS (bit depth >= 32) keeps float32.
_FRAME_STORE_SCALE = 65535.0
_FLOAT_STORE_BIT_DEPTH = 32
_UINT8_MAX = 255.0
#: Longest edge of the Style gallery's source image: two thumbnails side by side
#: on a phone at 2x density.
PRELOOK_THUMB_MAX_SIZE = 400


@dataclass(frozen=True)
class PreparedFrame:
    """A frame ready to write: packed pixels, metadata, and its thumbnail."""

    data: np.ndarray
    meta: dict[str, Any] = field(default_factory=dict)
    thumbnail: np.ndarray = field(default_factory=lambda: np.zeros((1, 1, 3), np.uint8))
    sky_matte: np.ndarray | None = None


def _pack_frame(data: np.ndarray, source_bit_depth: int) -> np.ndarray:
    """Frame data (nominal ``[0, 1]`` float) -> the compact on-disk dtype."""
    if source_bit_depth >= _FLOAT_STORE_BIT_DEPTH:
        return data.astype(np.float32)
    packed: np.ndarray = np.rint(np.clip(data, 0.0, 1.0) * _FRAME_STORE_SCALE).astype(np.uint16)
    return packed


def _unpack_frame(stored: np.ndarray) -> np.ndarray:
    """On-disk array -> ``float32`` in the ingest's nominal ``[0, 1]`` range."""
    scale = {np.dtype(np.uint16): _FRAME_STORE_SCALE, np.dtype(np.uint8): _UINT8_MAX}.get(
        stored.dtype, 1.0
    )
    out: np.ndarray = stored.astype(np.float32) / scale
    return out


class StorageService:
    """Owns paths and file IO for a session's working directory.

    Path getters never touch the filesystem; only ``save_*`` and ``layers_dir``
    create directories.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else get_settings().images_dir

    # -- paths ---------------------------------------------------------------

    def session_dir(self, session_id: str, *, create: bool = False) -> Path:
        path = self.root / session_id
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def original_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "original.jpg"

    def processed_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "processed.jpg"

    def preview_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "preview.jpg"

    def depth_dir(self, session_id: str, *, create: bool = False) -> Path:
        path = self.session_dir(session_id, create=create) / "depth"
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def depth_map_path(self, session_id: str) -> Path:
        return self.depth_dir(session_id) / "depth_map.png"

    def layer_path(self, session_id: str, index: int) -> Path:
        return self.depth_dir(session_id) / f"layer_{index}.png"

    # -- image IO ----------------------------------------------------------

    def save_original(self, session_id: str, image: np.ndarray) -> Path:
        """Persist the upload and initialise the processed/preview copies."""
        self.session_dir(session_id, create=True)
        image_utils.save_image(image, self.original_path(session_id), quality=95)
        self.save_result(session_id, image)
        return self.original_path(session_id)

    def save_result(self, session_id: str, image: np.ndarray) -> None:
        """Store a processed image plus its downscaled preview."""
        self.session_dir(session_id, create=True)
        image_utils.save_image(image, self.processed_path(session_id), quality=92)
        preview = image_utils.make_preview(image, get_app_settings().preview_max_size)
        image_utils.save_image(preview, self.preview_path(session_id), quality=85)

    def load_original(self, session_id: str) -> np.ndarray:
        return image_utils.load_image(self.original_path(session_id))

    def load_processed(self, session_id: str) -> np.ndarray:
        return image_utils.load_image(self.processed_path(session_id))

    # -- pre-look render (the "Style" step) -------------------------------

    def prelook_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "prelook.npy"

    def _prelook_key_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "prelook.json"

    def prelook_thumb_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "prelook_thumb.png"

    def save_prelook(self, session_id: str, image: np.ndarray, key: str) -> None:
        """Keep the result before its look, losslessly, tagged with the edit ``key``.

        The look is a final layer: re-rendering only its amount, the gallery
        thumbnails, and an export without the look all start from this.
        """
        self.session_dir(session_id, create=True)
        np.save(self.prelook_path(session_id), image.astype(np.uint8, copy=False))
        thumb = image_utils.make_preview(image, PRELOOK_THUMB_MAX_SIZE)
        image_utils.save_image(thumb, self.prelook_thumb_path(session_id))
        self._prelook_key_path(session_id).write_text(json.dumps({"key": key}), encoding="utf-8")

    def load_prelook(self, session_id: str, key: str | None = None) -> np.ndarray | None:
        """The stored pre-look result, or ``None``.

        With ``key``, only when it was produced by that same edit (anything but
        the look unchanged) - otherwise the cache is stale.
        """
        path = self.prelook_path(session_id)
        if not path.exists():
            return None
        if key is not None:
            key_path = self._prelook_key_path(session_id)
            if not key_path.exists():
                return None
            if json.loads(key_path.read_text(encoding="utf-8")).get("key") != key:
                return None
        image: np.ndarray = np.load(path)
        return image

    def load_prelook_thumb(self, session_id: str) -> np.ndarray | None:
        path = self.prelook_thumb_path(session_id)
        if not path.exists():
            return None
        return image_utils.load_image(path)

    # -- depth artifacts -------------------------------------------------

    def save_depth(self, session_id: str, depth_map: np.ndarray, layers: list[np.ndarray]) -> None:
        """Write the depth map and replace any cached parallax layers."""
        depth_dir = self.depth_dir(session_id, create=True)
        for stale in depth_dir.glob("layer_*.png"):
            stale.unlink()
        image_utils.save_image(depth_map, self.depth_map_path(session_id))
        for index, layer in enumerate(layers):
            image_utils.save_image(layer, self.layer_path(session_id, index))

    def load_depth_map(self, session_id: str) -> np.ndarray:
        return image_utils.load_image_gray(self.depth_map_path(session_id))

    def has_depth(self, session_id: str) -> bool:
        return self.depth_map_path(session_id).exists()

    def count_layers(self, session_id: str) -> int:
        return len(list(self.depth_dir(session_id).glob("layer_*.png")))

    # -- stacking: paths ---------------------------------------------------

    def stack_dir(self, stack_id: str, *, create: bool = False) -> Path:
        path = self.root / "stacks" / stack_id
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def stack_frames_dir(self, stack_id: str, *, create: bool = False) -> Path:
        path = self.stack_dir(stack_id) / "frames"
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def stack_accum_dir(self, stack_id: str, *, create: bool = False) -> Path:
        """Where the streaming-integration memmap accumulators live (Phase 1)."""
        path = self.stack_dir(stack_id) / "accum"
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def linear_frame_path(self, stack_id: str, index: int) -> Path:
        return self.stack_frames_dir(stack_id) / f"{index:0{_FRAME_INDEX_WIDTH}d}.npy"

    def _frame_meta_path(self, stack_id: str, index: int) -> Path:
        return self.stack_frames_dir(stack_id) / f"{index:0{_FRAME_INDEX_WIDTH}d}.json"

    def _frame_sky_matte_path(self, stack_id: str, index: int) -> Path:
        return self.stack_frames_dir(stack_id) / f"{index:0{_FRAME_INDEX_WIDTH}d}_sky.npy"

    def load_frame_sky_matte(self, stack_id: str, index: int) -> np.ndarray | None:
        """A stored frame's sky matte, or ``None`` when its file had none."""
        path = self._frame_sky_matte_path(stack_id, index)
        if not path.exists():
            return None
        matte: np.ndarray = np.load(path)
        return matte

    def stack_thumb_path(self, stack_id: str, index: int) -> Path:
        return self.stack_frames_dir(stack_id) / f"{index:0{_FRAME_INDEX_WIDTH}d}_thumb.jpg"

    def stack_composite_path(self, stack_id: str) -> Path:
        """The 32-bit linear composite (``.npy``), before any stretch/enhancement."""
        return self.stack_dir(stack_id) / "composite.npy"

    # -- stacking: calibration frames (Phase 2) --------------------------

    def stack_cal_root(self, stack_id: str, *, create: bool = False) -> Path:
        """Where master calibration frames and the bad-pixel map live."""
        path = self.stack_dir(stack_id) / "cal"
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def stack_cal_dir(self, stack_id: str, kind: str, *, create: bool = False) -> Path:
        path = self.stack_cal_root(stack_id) / kind
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def cal_frame_path(self, stack_id: str, kind: str, index: int) -> Path:
        return self.stack_cal_dir(stack_id, kind) / f"{index:0{_FRAME_INDEX_WIDTH}d}.npy"

    def _cal_meta_path(self, stack_id: str, kind: str, index: int) -> Path:
        return self.stack_cal_dir(stack_id, kind) / f"{index:0{_FRAME_INDEX_WIDTH}d}.json"

    def master_path(self, stack_id: str, kind: str) -> Path:
        return self.stack_cal_root(stack_id) / f"master_{kind}.npy"

    def master_meta_path(self, stack_id: str, kind: str) -> Path:
        return self.stack_cal_root(stack_id) / f"master_{kind}.json"

    def bad_pixel_map_path(self, stack_id: str) -> Path:
        return self.stack_cal_root(stack_id) / "bad_pixels.npy"

    def save_cal_frame(self, stack_id: str, kind: str, index: int, frame: LinearFrame) -> None:
        """Persist one calibration sub as a compact ``.npy`` + a small metadata sidecar."""
        self.stack_cal_dir(stack_id, kind, create=True)
        np.save(
            self.cal_frame_path(stack_id, kind, index),
            _pack_frame(frame.data, frame.source_bit_depth),
        )
        self._cal_meta_path(stack_id, kind, index).write_text(
            json.dumps(
                {
                    "is_cfa": frame.is_cfa,
                    "bayer_pattern": frame.bayer_pattern,
                    "source_bit_depth": frame.source_bit_depth,
                    "acquisition": frame.metadata,
                }
            ),
            encoding="utf-8",
        )

    def load_cal_frame(self, stack_id: str, kind: str, index: int) -> LinearFrame:
        meta = json.loads(self._cal_meta_path(stack_id, kind, index).read_text(encoding="utf-8"))
        return LinearFrame(
            data=_unpack_frame(np.load(self.cal_frame_path(stack_id, kind, index))),
            is_cfa=bool(meta.get("is_cfa", False)),
            bayer_pattern=meta.get("bayer_pattern"),
            source_bit_depth=int(meta.get("source_bit_depth", 16)),
            metadata=dict(meta.get("acquisition", {})),
        )

    def load_cal_acquisition(self, stack_id: str, kind: str, index: int) -> dict[str, Any]:
        meta = json.loads(self._cal_meta_path(stack_id, kind, index).read_text(encoding="utf-8"))
        return dict(meta.get("acquisition", {}))

    def cal_frame_indices(self, stack_id: str, kind: str) -> list[int]:
        directory = self.stack_cal_dir(stack_id, kind)
        if not directory.exists():
            return []
        return sorted(int(p.stem) for p in directory.glob("[0-9]" * _FRAME_INDEX_WIDTH + ".npy"))

    def cal_frame_counts(self, stack_id: str) -> dict[str, int]:
        return {kind: len(self.cal_frame_indices(stack_id, kind)) for kind in _CALIBRATION_KINDS}

    def clear_cal_kind(self, stack_id: str, kind: str) -> None:
        """Drop every sub of one kind and any master / bad-pixel map derived from it."""
        directory = self.stack_cal_dir(stack_id, kind)
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
        for stale in (
            self.master_path(stack_id, kind),
            self.master_meta_path(stack_id, kind),
            self.bad_pixel_map_path(stack_id),
            self.bad_pixel_map_path(stack_id).with_suffix(".json"),
        ):
            stale.unlink(missing_ok=True)

    # -- stacking: linear frame store ------------------------------------

    def prepare_linear_frame(self, frame: LinearFrame) -> PreparedFrame:
        """The CPU-heavy half of persisting a frame (packing + the thumbnail),
        with no filesystem or DB touch - safe to run across a threadpool."""
        return PreparedFrame(
            data=_pack_frame(frame.data, frame.source_bit_depth),
            meta={
                "is_cfa": frame.is_cfa,
                "bayer_pattern": frame.bayer_pattern,
                "source_bit_depth": frame.source_bit_depth,
                "already_stretched": frame.already_stretched,
                "acquisition": frame.metadata,
            },
            thumbnail=to_display_bgr(frame, _STACK_THUMB_MAX_SIZE),
            sky_matte=frame.sky_matte,
        )

    def write_linear_frame(self, stack_id: str, index: int, prepared: PreparedFrame) -> None:
        """Write a :meth:`prepare_linear_frame` result to disk (fast: three files,
        plus the frame's sky matte when it has one - a replaced frame never keeps
        the previous one's)."""
        self.stack_frames_dir(stack_id, create=True)
        matte_path = self._frame_sky_matte_path(stack_id, index)
        if prepared.sky_matte is not None:
            np.save(matte_path, prepared.sky_matte.astype(np.uint8))
        else:
            matte_path.unlink(missing_ok=True)
        np.save(self.linear_frame_path(stack_id, index), prepared.data)
        self._frame_meta_path(stack_id, index).write_text(
            json.dumps(prepared.meta), encoding="utf-8"
        )
        image_utils.save_image(
            prepared.thumbnail, self.stack_thumb_path(stack_id, index), quality=80
        )

    def save_linear_frame(self, stack_id: str, index: int, frame: LinearFrame) -> None:
        """Persist one ingested frame: a compact ``.npy`` + a metadata sidecar + a thumbnail."""
        self.write_linear_frame(stack_id, index, self.prepare_linear_frame(frame))

    def load_linear_frame(self, stack_id: str, index: int) -> LinearFrame:
        meta = json.loads(self._frame_meta_path(stack_id, index).read_text(encoding="utf-8"))
        data = _unpack_frame(np.load(self.linear_frame_path(stack_id, index)))
        return LinearFrame(
            data=data,
            is_cfa=bool(meta["is_cfa"]),
            bayer_pattern=meta["bayer_pattern"],
            source_bit_depth=int(meta["source_bit_depth"]),
            already_stretched=bool(meta["already_stretched"]),
            metadata=dict(meta.get("acquisition", {})),
        )

    def load_frame_acquisition(self, stack_id: str, index: int) -> dict[str, Any]:
        """The metadata sidecar for one frame (acquisition keywords, CFA flags)."""
        return dict(json.loads(self._frame_meta_path(stack_id, index).read_text(encoding="utf-8")))

    def has_linear_frame(self, stack_id: str, index: int) -> bool:
        return self.linear_frame_path(stack_id, index).exists()

    def stack_frame_indices(self, stack_id: str) -> list[int]:
        """Sorted indices of every frame currently on disk for this stack."""
        frames_dir = self.stack_frames_dir(stack_id)
        if not frames_dir.exists():
            return []
        return sorted(int(p.stem) for p in frames_dir.glob("[0-9]" * _FRAME_INDEX_WIDTH + ".npy"))

    def save_stack_composite(self, stack_id: str, composite: np.ndarray) -> None:
        self.stack_dir(stack_id, create=True)
        np.save(self.stack_composite_path(stack_id), composite.astype(np.float32))

    def stack_composite_shape(self, stack_id: str) -> tuple[int, ...]:
        """The composite's array shape, read from the file header without loading it."""
        composite = np.load(self.stack_composite_path(stack_id), mmap_mode="r")
        return tuple(int(n) for n in composite.shape)

    def load_stack_composite(self, stack_id: str) -> np.ndarray:
        composite: np.ndarray = np.load(self.stack_composite_path(stack_id))
        return composite

    def stack_sky_mask_path(self, stack_id: str) -> Path:
        """A nightscape's sky mask (``uint8``, 255 = sky), when the composite has one."""
        return self.stack_dir(stack_id) / "sky_mask.npy"

    def save_stack_sky_mask(self, stack_id: str, mask: np.ndarray) -> None:
        self.stack_dir(stack_id, create=True)
        np.save(self.stack_sky_mask_path(stack_id), mask.astype(np.uint8))

    def stack_render_hints_path(self, stack_id: str) -> Path:
        """What the source frames say about rendering the composite (JSON)."""
        return self.stack_dir(stack_id) / "render_hints.json"

    def save_stack_render_hints(self, stack_id: str, hints: dict[str, Any]) -> None:
        self.stack_dir(stack_id, create=True)
        self.stack_render_hints_path(stack_id).write_text(json.dumps(hints), encoding="utf-8")

    def load_stack_render_hints(self, stack_id: str) -> dict[str, Any] | None:
        path = self.stack_render_hints_path(stack_id)
        if not path.exists():
            return None
        return dict(json.loads(path.read_text(encoding="utf-8")))

    def delete_stack_sky_mask(self, stack_id: str) -> None:
        self.stack_sky_mask_path(stack_id).unlink(missing_ok=True)

    def load_stack_sky_mask(self, stack_id: str) -> np.ndarray | None:
        path = self.stack_sky_mask_path(stack_id)
        if not path.exists():
            return None
        mask: np.ndarray = np.load(path)
        return mask

    def delete_stack(self, stack_id: str) -> None:
        path = self.stack_dir(stack_id)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)

    def stack_ids_on_disk(self) -> list[str]:
        """Every stack directory under ``stacks/`` - to find dirs with no DB row."""
        root = self.root / "stacks"
        if not root.exists():
            return []
        return [p.name for p in root.iterdir() if p.is_dir()]

    def stack_accum_mtime(self, stack_id: str) -> float | None:
        """Newest mtime of anything in the stack's ``accum/`` dir, or ``None``.

        A live integration writes the align-memmap in one streaming pass and
        deletes it in a ``finally``; a stale mtime means the run died.
        """
        accum = self.stack_accum_dir(stack_id)
        if not accum.exists():
            return None
        mtimes = [child.stat().st_mtime for child in accum.iterdir()]
        return max(mtimes) if mtimes else accum.stat().st_mtime

    def delete_stack_accum(self, stack_id: str) -> None:
        accum = self.stack_accum_dir(stack_id)
        if accum.exists():
            shutil.rmtree(accum, ignore_errors=True)

    # -- lifecycle -------------------------------------------------------

    def has_session(self, session_id: str) -> bool:
        return self.original_path(session_id).exists()

    def delete_session(self, session_id: str) -> None:
        """Remove a session's directory and everything under it."""
        path = self.session_dir(session_id)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            logger.info("session storage removed", session_id=session_id)
