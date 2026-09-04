# Changelog

All notable changes to MyAstroShine are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project aims to
adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

First implementation pass covering the full v1.0 + v1.1 roadmap. Nothing has been
tagged yet.

### Added

#### Core enhancement (Sprint 1-3)

- Image upload with format/size validation, 512 px preview generation, per-channel
  histogram, and session tracking (`POST /api/upload`, `GET /api/preview/{id}`).
- `ImageProcessingService` pipeline: geometry (rotate / flip / straighten /
  crop), white balance (temperature/tint), contrast, brightness,
  highlights/shadows recovery, saturation, vibrance, clarity, denoise
  (bilateral), star reduction (top-hat star mask + morphological erosion),
  sharpness. Validated against documented bounds.
- `POST /api/process/{id}` applies parameters and returns a job handle.
- `GET /api/health` system health check.
- Alembic migration scaffolding; `init_db()` creates tables for local/dev use.

#### Job queue and progress (Sprint 3)

- `PROCESSING_MODE` setting: `sync` (run in the request, default) or `queue`
  (Celery task on Redis).
- Celery app and tasks (`task_process_image`, `task_process_stack`,
  `task_cleanup_sessions`); `task_always_eager` under `APP_ENV=test`.
- `JobRecord` tracking with per-step progress; Redis pub/sub bridge.
- `WS /ws/processing-status/{job_id}` and `WS /ws/stack-status/{job_id}`: DB
  catch-up on connect, then live relay until a terminal status.

#### Presets (Sprint 3)

- `PresetService` with five built-ins (Nebula, Galaxy, Deep Field, Lunar,
  Cluster); built-ins cannot be deleted.
- `GET/POST /api/presets`, `DELETE /api/presets/{id}`,
  `POST /api/presets/{id}/apply/{session_id}`.
- Duplicate-name and quota (50 user presets) guards.

#### Depth Shift (Sprint 4)

- `DepthMapService`: Sobel-gradient depth map, normalization/smoothing, depth
  statistics.
- Parallax layer generation (2-12 BGRA layers, far to near).
- `POST /api/depth-shift/{id}`, plus metadata, depth-map, and per-layer endpoints.

#### AstroDex integration (Sprint 4)

- `AstroDexService`: canonical-JSON HMAC-SHA256 signing, payload composition,
  retry with exponential backoff on 5xx.
- `POST /api/astrodex/receive` (inbound image) and `POST /api/send-to-astrodex`
  (outbound signed webhook, delivered in the background).
- Long-lived bearer webhook tokens with per-token signing secrets, created and
  revoked from the Settings UI (`GET/POST /api/tokens`, `DELETE /api/tokens/{id}`).
- Callback-URL allowlist (`ASTRODEX_CALLBACK_URLS`).

#### Stacking (Sprint 6-7)

- `RegistrationService`: SIFT/ORB keypoints, Lowe ratio test, RANSAC homography,
  perspective warp.
- `NormalizationService` (background-level equalization) and `CosmicRayService`
  (MAD-based robust sigma rejection with an absolute-deviation floor).
- `CombinationService`: NaN-aware median, mean, and iterative sigma-clip;
  SNR-improvement estimate (~sqrt(N)).
- `POST /api/stack/initiate`, `POST /api/stack/{id}/upload-frame`,
  `POST /api/stack/{id}/process`, `GET /api/stack/{id}`. The composite is a normal
  session and can be enhanced, previewed, and downloaded.

#### Frontend

- React 19 + TypeScript + Vite single-page app, Tailwind CSS v4 (CSS-first).
- "Darkroom / neutre pro" design system (`docs/DESIGN.md`): semantic token layer
  and shared component classes (`.panel`, `.btn`, `.field`, `.slider`,
  `.segmented`, `.chip`, `.dropzone`) in `src/styles/index.css`. Dark-only.
- Single-image editor: drag-and-drop upload, before/after split preview with zoom
  controls, histogram, grouped parameter sliders (500 ms debounce), preset
  buttons, "save as preset" dialog, download.
- Crop / rotate tool (`CropTool`): full-screen mode with a draggable crop
  rectangle (corner + edge handles), straighten dial (+/-45 deg), 90 deg rotate,
  horizontal / vertical flip, and aspect presets (Free / Original / 1:1 / 16:9 /
  3:2 / 4:5 / 5:4). Commits a `geometry` object applied first in the pipeline.
- Preset chips: apply, plus a two-step delete on user presets (built-ins have no
  delete affordance; the backend also rejects it with 403).
- Interactive Depth Shift viewer (pointer-driven parallax, intensity slider).
- Multi-frame stacking mode: frame upload list, settings panel (alignment,
  combination, cosmic-ray/background toggles), step-by-step progress over the
  WebSocket, results panel with statistics, and "enhance composite" handoff.
- Webhook token manager (create with one-time secret display, revoke).
- AstroDex context detection from URL parameters and "send to AstroDex" action.
- snake_case <-> camelCase conversion isolated to the API/WS clients.

#### Tooling and infra

- `scripts/check_deps_fresh.py`: fails when any pin falls behind PyPI/npm; run in
  `pytest` and a weekly CI job.
- Docker Compose (`api`, `worker`, `web`, `redis`) and a hot-reload
  `docker-compose.dev.yml`.
- Playwright end-to-end suite (`npm run test:e2e`): upload -> slider -> process
  -> download, save-as-preset, and the full three-frame stacking flow with the
  "enhance composite" handoff. Boots the real backend and Vite dev server.
- GitHub Actions: backend (ruff, mypy, pytest), frontend (lint, typecheck, test,
  build), and e2e (Playwright) jobs, plus the dependency-freshness cron.
- API listens on port 8002.
- Initial Alembic revision (`606a1e113989_create_core_tables`) covering all six
  tables; `alembic upgrade head` / `downgrade base` and `alembic check` verified
  clean against the ORM models.

#### API rate limiting

- Per-IP request-rate limit (default 120/min, in-memory fixed window) on
  `/upload`, `/process/{id}`, `/presets/{id}/apply/{session_id}`, and
  `/stack/*`; over the limit returns `429 RATE_LIMITED`. (Shipped at the API
  spec's original 10/min first; raised the same day after it broke e2e and
  would have broken real interactive editing - the editor re-processes on
  every debounced slider change.)
- Per-IP concurrent-job limit (default 5), checked against the shared `jobs`
  table so it holds under both `sync` and `queue` processing modes.
- `rate_limit_enabled` / `rate_limit_per_minute` / `max_concurrent_jobs_per_ip`
  in Settings -> Advanced; `JobRecord.client_ip` (new Alembic revision
  `623faa14df02_add_job_client_ip`).

#### Session-cleanup scheduler

- `worker` runs Celery beat embedded (`-B`, both compose files): hourly,
  `task_cleanup_sessions` deletes sessions past `session_expiry_hours` and
  their files, regardless of `PROCESSING_MODE`. Schedule state persisted at
  `DATA_DIR/celerybeat-schedule`.

#### Performance benchmark suite

- `backend/tests/benchmarks/`: codifies the Success Metrics acceptance
  criteria as runnable checks - full-res (~24MP) enhance (measured 3.0s vs a
  5s budget), preview (512px) reprocess (38ms vs 500ms), and an empirical
  stacking-SNR check (16 synthetic frames with known noise through
  `combine(..., "mean")`, measured 3.99x vs a theoretical 4.00x). Opt-in
  (`RUN_BENCHMARKS=1 pytest tests/benchmarks --no-cov`) rather than part of
  the default suite, since wall-clock budgets are sensitive to the machine and
  to coverage instrumentation; runs weekly via
  `.github/workflows/benchmarks.yml`, not on every push/PR.

### Changed

#### Configuration moved out of the environment (PASSATION alignment, part 1)

- `docker compose up` now needs no `.env` editing. The compose files carry only
  structural variables (`APP_ENV`, `DATA_DIR`, `PROCESSING_MODE`, the Redis URLs);
  `docker-compose.yml` dropped from 11 backend variables to 6 and holds no
  secrets.
- Single persistence root `DATA_DIR` (`/data` in the image). The database,
  session images, stacking frames, cache, log file, `secret_key.txt` and
  `app_settings.json` all derive from it; the two data volumes were merged into
  one (`myastroshine_data`).
- The session / HMAC-fallback secret is generated once into
  `DATA_DIR/secret_key.txt` (`secrets.token_hex(32)`) and never regenerated.
  `ASTRODEX_WEBHOOK_SECRET` is gone.
- New `app_settings.json` holds every runtime-tunable value (CORS origins,
  AstroDex callback allowlist and retry policy, upload limit, session lifetime,
  preview size, ML denoise, depth method, stacking defaults, log levels). It is
  edited from a rebuilt **Settings** screen (General / Webhooks / Advanced tabs)
  via `GET`/`POST /api/admin/app-settings`, gated by `ADMIN_ENABLED`.
- `app/config.py` now exposes only the deployment shape; product settings come
  from `app/utils/app_settings.py` (`get_app_settings()` / `save_app_settings()`
  / `reload_app_settings()`). `DATABASE_URL` stays as an optional override for
  Postgres.
- `docs/DEPLOYMENT.md` rewritten around this split (structural env table +
  "where to set it in the UI" table).

#### Settings is its own page

- Settings moved out of the editor into a standalone route (`#/settings`) with a
  section rail (General / Webhooks / Advanced), labelled rows with descriptions,
  toggle switches, and a sticky save bar. `useAppSettings` holds a draft and
  posts the whole object back.

#### Visual charter aligned with MyAstroBoard (PASSATION alignment, part 5)

- `docs/DESIGN.md` rewritten: the sky/teal primary accent (`#38bdf8`), the amber
  ecosystem accent (`#f59e0b`, used for AstroDex actions), deep navy-teal
  surfaces, a fixed background gradient with two ambient halos, and glass panels
  - the charter now shared with MyAstroBoard. The image still stays the loudest
  thing on screen.
- Token layer in `frontend/src/styles/index.css` reworked accordingly; new
  `amber*` tokens, `--gradient-accent`, `--shadow-glass` / `--shadow-premium`,
  and a `.btn-amber` modifier. `.btn-primary` is now the teal gradient. No
  component markup changed - everything is token-driven.

#### Logging: rotating file sink + admin controls (PASSATION alignment, part 4)

- `get_logger()` now renders through the stdlib, so alongside the console there
  is a rotating file at `DATA_DIR/myastroshine.log` (10 MB x 5) - and
  `worker.log` for the Celery worker. Line format carries the timestamp in the
  `TZ` zone with the UTC offset, the module, level, and `[func:line]`.
- Independent console and file levels (`console_log_level` default `warning`,
  `log_level` default `info`), changeable at runtime - `apply_runtime_log_levels`
  runs at startup and after any settings write; noisy libraries (`httpx`, `PIL`,
  ...) pinned to `warning`.
- New endpoints: `GET /api/admin/logs` (tail, newest first, `level` filter),
  `GET`/`POST /api/admin/logs/level`, `POST /api/admin/logs/clear`,
  `GET /api/admin/logs/export` (ZIP of the logs + rotations + worker log).
- Settings gains a **Logs** section: live tail, level filter, clear, export ZIP.

### Fixed

- Editor preview now refreshes after every adjustment: `useImageProcessing`
  exposes a `previewVersion` that the processed-image URL carries as a
  cache-buster (the URL was otherwise constant, so the browser kept the first
  render).
- Applying a preset now also moves the sliders to the preset's values
  (`syncParameters`), so a follow-up tweak starts from the preset; a manual
  slider edit (or Reset all) drops the preset highlight (`clearActivePreset`).
- Before/after divider: the whole frame is a grab zone with an `ew-resize`
  cursor and a centre handle; dragging no longer selects the page (images are
  `draggable={false}` / `pointer-events-none`, container is `select-none` and
  captures the pointer).
- Before/after view compares the true upload against the result:
  `GET /preview/{id}?original=true` serves the untouched original, and the two
  images share one box via `clip-path` so they stay aligned. The preview frame
  now takes the image's real aspect ratio instead of a fixed 16:9 letterbox.
  Once a crop/rotate/flip/straighten changes the result's frame, the "before"
  side switches to `?original=true&geometry=true`, which applies that same
  geometry to the original on the fly (no colour/tone enhancement) so the two
  stay aligned instead of the split disappearing.
- Depth Shift viewer is a centred modal (was an inline block pushed off-screen)
  and closes on Escape / backdrop click.
- Docker dev stack: Vite proxies `/api` and `/ws` to the `api` service
  (`VITE_PROXY_TARGET`), so backend-relative image URLs (depth layers, stacked
  composite) load instead of 502-ing. `VITE_API_URL`/`VITE_WS_URL` dropped from
  `docker-compose.dev.yml`; `ws.ts` builds an absolute ws:// URL from the page
  origin when unset.

### Known gaps

- The slider panel has no per-parameter tooltips.
- Nothing is tagged yet; no published Docker images or GitHub release.
