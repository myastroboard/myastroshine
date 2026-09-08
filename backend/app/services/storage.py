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

    # -- stacking: linear frame store ------------------------------------

    def save_linear_frame(self, stack_id: str, index: int, frame: LinearFrame) -> None:
        """Persist one ingested frame: float32 ``.npy`` + a metadata sidecar + a thumbnail."""
        self.stack_frames_dir(stack_id, create=True)
        np.save(self.linear_frame_path(stack_id, index), frame.data.astype(np.float32))
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
        data = np.load(self.linear_frame_path(stack_id, index))
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

    # -- lifecycle -------------------------------------------------------

    def has_session(self, session_id: str) -> bool:
        return self.original_path(session_id).exists()

    def delete_session(self, session_id: str) -> None:
        """Remove a session's directory and everything under it."""
        path = self.session_dir(session_id)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            logger.info("session storage removed", session_id=session_id)
