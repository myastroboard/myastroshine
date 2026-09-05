"""Fixed values that describe how the app is built, not how it is configured.

Deployment shape lives in :mod:`app.config`; user-tunable settings live in
``app_settings.json`` (see :mod:`app.utils.app_settings`).
"""

from __future__ import annotations

API_TITLE = "MyAstroShine"

# The API always listens here; 8000 is left free for other local projects.
API_PORT = 8002

# Logging - rotating file handler in DATA_DIR (see app/logging_config.py).
LOG_FILE_NAME = "myastroshine.log"
WORKER_LOG_FILE_NAME = "worker.log"
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
LOG_BACKUP_COUNT = 5  # myastroshine.log.1 .. .log.5

# Accepted log levels, low to high. First entry is the safe default.
LOG_LEVELS = ("debug", "info", "warning", "error", "critical")

# How often the Celery-beat schedule runs task_cleanup_sessions (app/tasks/celery_app.py).
# Independent of session_expiry_hours (app_settings.json): that decides which sessions are
# due for cleanup, this decides how often we look. Not user-tunable - nobody needs to.
SESSION_CLEANUP_INTERVAL_SECONDS = 60 * 60  # hourly

# Decoded-pixel-count cap (app/utils/image_utils.py:decode_image), independent of the
# compressed upload byte-size limit (max_image_size_mb) - guards against a small file
# that decompresses into a huge array (decompression bomb). 8000x8000, comfortably above
# the ~24MP frame used in tests/benchmarks/.
MAX_IMAGE_PIXELS = 8000 * 8000

# Update check (app/services/version_check.py) - how long the latest-GitHub-release
# result is cached before it is fetched again. Long enough to stay well under GitHub's
# unauthenticated rate limit regardless of how often the frontend polls.
GITHUB_RELEASES_URL = "https://api.github.com/repos/myastroboard/myastroshine/releases/latest"
VERSION_CHECK_CACHE_TTL_SECONDS = 4 * 60 * 60  # 4 hours
