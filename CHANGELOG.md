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
- `ImageProcessingService` pipeline: white balance (temperature/tint), contrast,
  brightness, highlights/shadows recovery, saturation, vibrance, clarity, denoise
  (bilateral), sharpness. Twelve parameters, validated against documented bounds.
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

### Known gaps

- API rate limiting is planned for a later release (per the API spec, v1.5+).
- Alembic has no versioned revisions; production migrations still to be authored.
- No load/performance benchmark suite.
