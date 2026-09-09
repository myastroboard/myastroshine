"""Fixed values that describe how the app is built, not how it is configured.

Deployment shape lives in :mod:`app.config`; user-tunable settings live in
``app_settings.json`` (see :mod:`app.utils.app_settings`).
"""

from __future__ import annotations

API_TITLE = "MyAstroShine"

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

# How often the watch-folder poll runs (app/services/stack_watch.py). A no-op
# unless stacking_watch_dir is set; the idle-to-process delay is user-tunable.
STACK_WATCH_INTERVAL_SECONDS = 60

# A processing job still non-terminal after this long has been abandoned (a worker died
# mid-run, or a queued job was never picked up). It stops counting toward the per-IP
# concurrency limit (app/services/job.py) and the hourly cleanup marks it failed - so a
# few stuck rows can't permanently brick processing for an IP. Well above the slowest
# real operation (a large multi-frame stack finishes in minutes).
STALE_JOB_SECONDS = 15 * 60

# A stack "processing" whose on-disk align-memmap (stacks/{id}/accum/) has not been
# touched for this long has a dead worker. The hourly cleanup deletes the memmap - a
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
