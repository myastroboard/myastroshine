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

import shutil
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.logging_config import get_logger
from app.utils import image_utils
from app.utils.app_settings import get_app_settings

logger = get_logger(__name__)


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

    def load_preview(self, session_id: str) -> np.ndarray:
        return image_utils.load_image(self.preview_path(session_id))

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

    # -- stacking (v1.1) -----------------------------------------------

    def stack_dir(self, stack_id: str, *, create: bool = False) -> Path:
        path = self.root / "stacks" / stack_id
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def stack_frame_path(self, stack_id: str, index: int) -> Path:
        return self.stack_dir(stack_id) / f"frame_{index:03d}.png"

    def save_stack_frame(self, stack_id: str, index: int, image: np.ndarray) -> None:
        self.stack_dir(stack_id, create=True)
        image_utils.save_image(image, self.stack_frame_path(stack_id, index))

    def load_stack_frames(self, stack_id: str) -> list[np.ndarray]:
        paths = sorted(self.stack_dir(stack_id).glob("frame_*.png"))
        return [image_utils.load_image(path) for path in paths]

    def count_stack_frames(self, stack_id: str) -> int:
        return len(list(self.stack_dir(stack_id).glob("frame_*.png")))

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
