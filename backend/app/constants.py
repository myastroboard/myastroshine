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
