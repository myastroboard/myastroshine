"""Fixed values that describe how the app is built, not how it is configured.

Deployment shape lives in :mod:`app.config`; user-tunable settings live in
``app_settings.json`` (see :mod:`app.utils.app_settings`).
"""

from __future__ import annotations

from pathlib import Path

API_TITLE = "MyAstroShine"

# Logging - rotating file handler in DATA_DIR (see app/logging_config.py).
LOG_FILE_NAME = "myastroshine.log"
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
LOG_BACKUP_COUNT = 5  # myastroshine.log.1 .. .log.5

# Accepted log levels, low to high. First entry is the safe default.
LOG_LEVELS = ("debug", "info", "warning", "error", "critical")

# How often the in-process scheduler runs the cleanup (app/services/scheduler.py).
# Independent of session_expiry_hours (app_settings.json): that decides which sessions are
# due for cleanup, this decides how often we look. Not user-tunable - nobody needs to.
SESSION_CLEANUP_INTERVAL_SECONDS = 60 * 60  # hourly

# How often the watch-folder poll runs (app/services/stack_watch.py). A no-op
# unless stacking_watch_dir is set; the idle-to-process delay is user-tunable.
STACK_WATCH_INTERVAL_SECONDS = 60

# A processing job still non-terminal after this long has been abandoned (its thread died
# mid-run, or a queued job was never picked up). It stops counting toward the per-IP
# concurrency limit (app/services/job.py) and the hourly cleanup marks it failed - so a
# few stuck rows can't permanently brick processing for an IP. Well above the slowest
# real operation (a large multi-frame stack finishes in minutes).
STALE_JOB_SECONDS = 15 * 60

# A stack "processing" whose on-disk align-memmap (stacks/{id}/accum/) has not been
# touched for this long has a dead job thread. The hourly cleanup deletes the memmap - a
# thousand-frame run leaves a ~10 GB float16 file - and marks the stack failed. The
# integration keeps the mtime fresh through every pass, so this only needs headroom
# over the gap between two progress ticks, not over a whole run.
STALE_STACK_WORK_SECONDS = 30 * 60

# An un-processed stack upload (waiting_for_frames / ready) older than this is
# abandoned. A smart-telescope night is thousands of full-res frames (8+ GB), so it is
# swept well before the normal 24 h session expiry.
ABANDONED_STACK_SECONDS = 4 * 60 * 60

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

# External ML engines - optional, operator-installed StarNet2 / DeepSNR, invoked as a
# subprocess (docs/DEPLOYMENT.md "External ML engines"). Nothing is bundled. These are the
# upstream versions this app's CLI invocation has been tested against, as half-open
# [min, max) ranges: a binary outside the range still runs, with a soft "untested"
# warning in Settings. Bump deliberately after a real-image test round. Verified
# 2026-09-09 on linux-x64: StarNet2 2.6.1 (ORT build 0232), DeepSNR 1.3.1.
STARNET2_TESTED_VERSIONS = ("2.6.0", "2.7.0")
DEEPSNR_TESTED_VERSIONS = ("1.3.0", "1.4.0")
# How long to wait for `<binary> --version` during the capability probe. Generous - a
# cold start of a self-contained ONNX-Runtime binary can be a few seconds.
ENGINE_PROBE_TIMEOUT_SECONDS = 15
# How long a single external-engine pass (StarNet2 / DeepSNR) may take before it is
# killed and the pipeline falls back to the classical stage. Measured: StarNet2
# ~19 s for 6.6 MP on a fast multi-core box, DeepSNR ~7 s; a 24 MP frame on a
# 2-core VPS can be several minutes, so this has real headroom - a timeout should
# mean "hung", not "slow".
EXTERNAL_ENGINE_TIMEOUT_SECONDS = 900
# StarNet2 and DeepSNR both reject an input smaller than this on either axis; a
# smaller image (a tiny preview, a crop) is upscaled to meet it and scaled back.
EXTERNAL_ENGINE_MIN_DIMENSION = 512

# Admin authentication (app.services.admin_auth). The cookie name is specific to
# this app: behind a Home Assistant ingress every app shares the HA origin, so a
# generic name like "session" would collide.
ADMIN_COOKIE_NAME = "myastroshine_admin"
#: Hard ceiling on an admin session's life, whatever the idle setting says.
ADMIN_SESSION_MAX_DAYS = 30
#: last_seen_at is only rewritten when older than this - an admin page fires
#: several calls per view, no need for a DB write on each one.
ADMIN_SESSION_TOUCH_SECONDS = 60
ADMIN_PASSWORD_MIN_LENGTH = 10
ADMIN_PASSWORD_MAX_LENGTH = 256
#: Login throttle, per client IP: this many failures inside the window locks
#: the IP out; each further lockout doubles, up to the cap.
LOGIN_MAX_FAILURES = 5
LOGIN_FAILURE_WINDOW_SECONDS = 60
LOGIN_LOCKOUT_BASE_SECONDS = 60
LOGIN_LOCKOUT_MAX_SECONDS = 60 * 60
#: An empty file of this name in the data directory - or, in the Home Assistant
#: app, in its config folder - clears the admin password at the next start.
ADMIN_RESET_MARKER = "reset-admin"
#: Where Home Assistant mounts the app's own config folder (``map: addon_config``).
HA_APP_CONFIG_DIR = Path("/config")

# Background jobs (app/services/job_runner.py), run inside the API process. Edits
# and stacks get separate pools so a long stack never blocks the editor.
EDIT_JOB_WORKERS = 2
STACK_JOB_WORKERS = 1
#: At shutdown, how long running jobs get to reach their next step and stop.
#: Kept well under a container stop timeout (Docker 10 s, the HA app's timeout).
JOB_SHUTDOWN_GRACE_SECONDS = 5

# Uploads (app/utils/uploads.py, StackingService.add_frames).
#: Frames a single upload-frames / calibration request may carry. The web UI
#: sends batches of this size (frontend useStackProcessing UPLOAD_BATCH_SIZE).
UPLOAD_BATCH_MAX_FILES = 20
#: Frames of one batch decoded at once - bounds the memory an upload takes to a
#: few frames whatever the batch size.
UPLOAD_INGEST_WORKERS = 4
#: Room for the multipart framing on top of the file bytes when a request's
#: Content-Length is checked against the upload cap.
MULTIPART_OVERHEAD_BYTES = 1024 * 1024

# Engine packages uploaded from Settings (app/services/engine_install.py).
#: The StarNet2 / DeepSNR CLI packages are ~130-300 MB compressed.
ENGINE_ARCHIVE_MAX_BYTES = 1024 * 1024 * 1024
ENGINE_UNPACKED_MAX_BYTES = 2 * 1024 * 1024 * 1024
ENGINE_ARCHIVE_MAX_ENTRIES = 5000
#: A staged (unpacked, not yet accepted) package is dropped after this long.
ENGINE_STAGING_MAX_AGE_SECONDS = 60 * 60
ENGINE_LICENSE_MAX_BYTES = 64 * 1024

# The production server (app/serve.py).
SERVER_PORT = 8002
#: How long open connections (WebSockets, a running upload) get to finish when the
#: container stops, before the lifespan stops the background jobs.
SERVER_SHUTDOWN_GRACE_SECONDS = 3
