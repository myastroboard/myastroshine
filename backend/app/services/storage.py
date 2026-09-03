"""StorageService - filesystem layout and IO for session working files.

Layout (per docs/ARCHITECTURE):
    {storage_path}/{session_id}/
        original.jpg      full-resolution upload
        processed.jpg     full-resolution latest result
        preview.jpg       downscaled processed image (fast display)
        layers/layer_{n}.png
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.logging_config import get_logger
from app.utils import image_utils

logger = get_logger(__name__)


class StorageService:
    """Owns paths and file IO for a session's working directory.

    Path getters never touch the filesystem; only ``save_*`` and ``layers_dir``
    create directories.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else get_settings().storage_path

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

    def layers_dir(self, session_id: str) -> Path:
        path = self.session_dir(session_id, create=True) / "layers"
        path.mkdir(parents=True, exist_ok=True)
        return path

    # -- image IO ----------------------------------------------------------

    def save_original(self, session_id: str, image: np.ndarray) -> Path:
        """Persist the upload and initialise the processed/preview copies."""
        self.session_dir(session_id, create=True)
        image_utils.save_image(image, self.original_path(session_id), quality=95)
        self.save_result(session_id, image)
        return self.original_path(session_id)

    def save_result(self, session_id: str, image: np.ndarray) -> None:
        """Store a processed image plus its downscaled preview."""
        settings = get_settings()
        self.session_dir(session_id, create=True)
        image_utils.save_image(image, self.processed_path(session_id), quality=92)
        preview = image_utils.make_preview(image, settings.preview_max_size)
        image_utils.save_image(preview, self.preview_path(session_id), quality=85)

    def load_original(self, session_id: str) -> np.ndarray:
        return image_utils.load_image(self.original_path(session_id))

    def load_processed(self, session_id: str) -> np.ndarray:
        return image_utils.load_image(self.processed_path(session_id))

    # -- lifecycle -------------------------------------------------------

    def has_session(self, session_id: str) -> bool:
        return self.original_path(session_id).exists()

    def delete_session(self, session_id: str) -> None:
        """Remove a session's directory and everything under it."""
        path = self.session_dir(session_id)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            logger.info("session storage removed", session_id=session_id)
