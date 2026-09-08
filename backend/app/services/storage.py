"""StorageService - filesystem layout and IO for session working files.

Layout (per docs/ARCHITECTURE):
    {DATA_DIR}/images/{session_id}/
        original.jpg      full-resolution upload
        processed.jpg     full-resolution latest result
        preview.jpg       downscaled processed image (fast display)
        depth/depth_map.png
        depth/layer_{n}.png    BGRA parallax layers, far (0) to near
"""

from __future__ import annotations

import json
import shutil
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
        return sorted(
            int(p.stem) for p in directory.glob("[0-9]" * _FRAME_INDEX_WIDTH + ".npy")
        )

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

    def save_linear_frame(self, stack_id: str, index: int, frame: LinearFrame) -> None:
        """Persist one ingested frame: a compact ``.npy`` + a metadata sidecar + a thumbnail."""
        self.stack_frames_dir(stack_id, create=True)
        np.save(
            self.linear_frame_path(stack_id, index),
            _pack_frame(frame.data, frame.source_bit_depth),
        )
        meta: dict[str, Any] = {
            "is_cfa": frame.is_cfa,
            "bayer_pattern": frame.bayer_pattern,
            "source_bit_depth": frame.source_bit_depth,
            "already_stretched": frame.already_stretched,
            "acquisition": frame.metadata,
        }
        self._frame_meta_path(stack_id, index).write_text(json.dumps(meta), encoding="utf-8")
        image_utils.save_image(
            to_display_bgr(frame, _STACK_THUMB_MAX_SIZE),
            self.stack_thumb_path(stack_id, index),
            quality=80,
        )

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

    def load_stack_composite(self, stack_id: str) -> np.ndarray:
        composite: np.ndarray = np.load(self.stack_composite_path(stack_id))
        return composite

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
