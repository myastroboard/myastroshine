"""MyAstroShine backend application package."""

import os
from pathlib import Path


def _read_version() -> str:
    """Resolve the running version: Docker build-time env var, else the repo-root
    VERSION file (local/dev checkouts), else an explicit dev fallback."""
    env_version = os.environ.get("APP_VERSION")
    if env_version:
        return env_version
    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip() or "0.0.0-dev"
    except OSError:
        return "0.0.0-dev"


__version__ = _read_version()
