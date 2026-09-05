# Changelog

All notable changes to MyAstroShine are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project aims to
adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Star reduction rebuilt on per-star detection (`StarDetectionService`, a
  thresholded top-hat + `cv2.connectedComponentsWithStats`, at native
  resolution, robust to ordinary sensor/JPEG noise) instead of a single
  image-wide top-hat mask, so only genuine stars are shrunk and diffuse
  nebulosity is never dimmed. Each star shrinks via erosion floored at its
  own local background, so it can't crush to a black dot or bloat into a flat
  pale disc at full strength. New `star_sensitivity` / `star_max_size`
  parameters tune what counts as a star.
- Star mask preview: `POST /api/star-mask/{session_id}` reports detected star
  positions for a live "N sources detected" overlay in the editor, toggled from
  the Stars panel.
- Auto Astro: a one-click "Auto Astro" button (`POST /api/auto-astro/{session_id}`)
  analyses the image's histogram and star density and applies a computed
  starting parameter set - crushing the background for depth/separation from
  the DSO, and a gentle, log-scaled star reduction that stays a sensible
  starting point across both sparse frames and busy deep-stacked fields -
  in place of manually dialing in every slider.
- Editor UX: the adjustment sliders are now 5 named, collapsible sections
  (Light/Colour/Detail/Stars/Depth) with a per-section reset and help text,
  instead of 7 flat, always-open, technically-named groups. A dedicated
  Export panel holds Download/Send to AstroDex next to the preview. A
  focal-point picker on the preview (click to set) now actually drives where
  the Depth Shift parallax centers - `focus_point` was accepted by the API
  before this but never used.
- i18n: FR + EN. Every frontend-owned UI string now goes through
  `useTranslation()`'s `t()`, backed by `frontend/src/i18n/translations/{en,fr}.json`
  (`en.json` is the reference language); a compact EN/FR selector sits in the
  header. Detects the browser language on first load, then persists the
  choice client-side. `scripts/validate_i18n.py` (new CI job) checks key
  parity, leaf types, and `{placeholder}` names between the two files.
  Backend-owned strings (API error messages, log lines) stay English-only.
- Permanent page footer (name, version, GitHub link - inspired by
  MyAstroBoard's own footer bar), replacing the version number that used to
  sit in the header. In-app update check folds into it: once a newer GitHub
  release is published, a discreet second line appears with a link to it and
  a "What's new" that opens the release notes in a modal, rendered from
  markdown (headings, bold, lists, links) rather than shown as raw
  `### `/`**` syntax. `GET /api/version/check-updates` (`VersionCheckService`)
  queries GitHub's releases API and caches the result in memory for 4 hours,
  so the frontend's 4-hourly poll can never translate into hitting GitHub's
  rate limit; every failure path (timeout, GitHub's own rate limit, a
  malformed response, ...) degrades to no notice rather than an error. The
  frontend re-verifies the version comparison itself before showing
  anything, so a stale/incorrect cache can never present as a downgrade.
- Tone curve editor: an interactive curve graph (drag points to reshape,
  double-click to add or remove a point) alongside the adjustment sliders.
  Backed by a new `curve_points` parameter and a monotone cubic Hermite
  spline LUT stage in the processing pipeline, so a handful of dragged
  points make a smooth curve - not a faceted polyline - and can never
  overshoot past a control point's value into crushed shadows or blown
  highlights.

## [0.1.0] - 2026-09-04

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
- Parameter tooltips: each slider gets a small "i" badge (hover or keyboard
  focus, screen-reader linked via `aria-describedby`) explaining what it does.
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

#### Release mechanics

- Root `VERSION` file is now the single source of truth for the app version
  (previously hardcoded separately in the backend and frontend); read via a
  build-time `APP_VERSION` / `VITE_APP_VERSION` Docker build argument, or
  straight from the file for local dev.
- **Single Docker image**: the root `Dockerfile` (multi-stage: Node builds
  the frontend, Python runs the API) replaces the previous two-image split
  (`backend/Dockerfile` + `frontend/Dockerfile` behind nginx). FastAPI now
  serves the built React SPA directly (`StaticFiles`, mounted after every
  `/api`/`/ws` route - the frontend's hash-based routing needs no
  SPA-fallback handling), with `GZipMiddleware` and the security response
  headers nginx used to add (`X-Frame-Options`, `X-Content-Type-Options`,
  `Referrer-Policy`) moved into `app/main.py`. A `target: backend` build
  (skips the frontend stage) serves `worker` and the dev `api` service, which
  never need the built UI. One less container, one URL (`:8002`) for
  everything instead of `:8002` (API) + `:3000` (nginx).
- `.github/workflows/release.yml`: tag-triggered (`v*.*.*`) multi-arch build
  and push of the one image to **both** `ghcr.io/myastroboard/myastroshine`
  and Docker Hub's `myastroboard/myastroshine`, a Trivy scan, and a GitHub
  Release generated from this changelog.
- `.github/workflows/post-release-cleanup.yml`: opens a PR that files this
  section under a dated release heading after a successful publish
  (`scripts/changelog_release.py`).
- `CODE_OF_CONDUCT.md`, `SECURITY.md`.
- `docker-compose.yml` gained `image:` alongside `build:` on `api` so a clean
  machine can `docker compose up` from the published image without cloning
  the repo; see `docs/DEPLOYMENT.md`.

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
- `mypy`: `packages = ["app"]` already kept the CI command (`mypy app`) from
  ever touching `tests/`, but an IDE's mypy integration analyzes whatever file
  is open regardless of that scoping, so every untyped pytest fixture/test
  function surfaced as a strict-mode error there. Added a `tests.*` override
  (relaxed the same way ruff already special-cases `tests/*`) - fixed ~130
  false positives; the handful of real ones left (a couple of loosely-typed
  numpy assignments, a duck-typed fake `Request` in the rate-limit tests) were
  fixed properly instead of suppressed.

### Security

#### Release-hardening pass

- AstroDex callback-URL allowlist now fails closed: an empty
  `astrodex_callback_urls` rejects every callback URL (previously it allowed
  any), closing an SSRF path through `/api/send-to-astrodex` and
  `/api/astrodex/receive`.
- `/api/tokens` and the previously-ungated `GET /api/admin/app-settings` /
  `GET /api/admin/logs*` now require `ADMIN_ENABLED` like their sibling write
  routes already did.
- `cors_origins` rejects a literal `"*"` entry - the API always sets
  `allow_credentials=True`, so a wildcard origin would be a real hole, not
  just a combination browsers already reject.
- Decoded image dimensions are capped (`MAX_IMAGE_PIXELS`, 64MP) in addition
  to the existing compressed-upload-size limit, closing a decompression-bomb
  path in `decode_image`.
- Rate limiting now covers `/api/tokens`, `/api/admin/*`, `/api/download/*`,
  and the AstroDex routes (previously only upload/process/stack/preset-apply).
- Removed the dead `DEBUG` setting (never read anywhere; misleadingly implied
  a debug mode that didn't exist).
- `pip-audit` and `npm audit --audit-level=high` run in CI; a Trivy scan runs
  against every published image. See `SECURITY.md` for the full policy.

### Known gaps

- Nothing is tagged yet; no published Docker images or GitHub release.
- `depthShiftIntensity` (a `ProcessingParameters` field with its own slider) is
  dead: nothing in the enhancement pipeline or `depth_shift.py` reads it. The
  actual Depth Shift viewer has its own separate intensity state
  (`useDepthShift`). Found while adding parameter tooltips; not fixed since it
  needs a product decision (most likely: wire it as that viewer's starting
  value), not a copy change.

