# Architecture

How MyAstroShine is put together: the runtime topology, the request paths for a
single-image edit and a stack, the storage layout, and the module boundaries the
code holds to.

## Contents

- [One image, three services](#one-image-three-services)
- [Processing modes](#processing-modes)
- [The FastAPI application](#the-fastapi-application)
- [Backend layers](#backend-layers)
- [Request path: a single-image edit](#request-path-a-single-image-edit)
- [Request path: a stack](#request-path-a-stack)
- [Progress over WebSockets](#progress-over-websockets)
- [Database](#database)
- [Storage layout](#storage-layout)
- [Background schedule](#background-schedule)
- [Frontend](#frontend)
- [AstroDex integration](#astrodex-integration)

## One image, three services

Everything ships in **one Docker image**, built from the single root
`Dockerfile` (multi-stage: a Node stage builds the React app to `dist/`, a Python
stage runs FastAPI and, in the default final stage, also serves that built SPA).
`docker-compose.yml` runs three services from it:

| Service | Role | Port |
|---------|------|------|
| `api` | FastAPI under uvicorn - the REST API, the progress WebSockets, and the static web UI, all on one port | 8002 |
| `worker` | Celery worker with an embedded beat scheduler (`-B`) - runs queued processing jobs and the hourly cleanup. Built with `target: backend`, so it skips the frontend build | - |
| `redis` | Celery broker **and** the progress pub/sub channel | 6379 |

`api` and `worker` run the *same* service code (`app/services/*`); the only
difference is who calls it - the HTTP request thread, or the Celery task. Both
mount the same data volume and the same optional `./engines` directory.

## Processing modes

`PROCESSING_MODE` decides where the pixel work happens:

- **`sync`** (the default, and what local `uvicorn` and the tests use) - the
  pipeline runs inside the HTTP request. No worker or Redis needed. The job row
  is already `completed` when `/process` returns.
- **`queue`** (what `docker-compose.yml` sets) - `/process` and
  `/stack/{id}/process` enqueue a Celery task and return immediately with a
  `queued` job; the `worker` runs it and streams progress through Redis.

The rest of the app is identical in both modes - the same `JobRecord` lifecycle,
the same WebSocket contract, the same results on disk.

## The FastAPI application

`app/main.py:create_app()` wires:

- **CORS** (`cors_origins`, credentials on - a literal `"*"` is rejected),
  **GZip**, and a small middleware that adds the security headers a reverse proxy
  would normally supply (`X-Frame-Options`, `X-Content-Type-Options`, ...).
- A **shared error envelope**: every `AppError` and request-validation failure is
  rendered as `{ error, error_code, details, request_id, timestamp }` (see
  [API.md](API.md)). No stack traces or paths leak into a response.
- The **API routers**, all mounted under `/api`.
- The **WebSocket router** at the root (`/ws/...`), to match the frontend
  contract and a reverse-proxy `/ws/` location.
- The **built SPA** mounted last at `/` (only when the image was built with the
  frontend stage). Route order means every `/api` and `/ws` path still wins; the
  SPA uses hash routing so a plain static mount is enough.

Startup (`lifespan`) configures logging, creates the data tree, loads or
generates the session secret, applies the runtime log levels, runs
`init_db()`, and seeds the five built-in presets.

## Backend layers

```
routes/      HTTP + WebSocket handlers - parse, validate, delegate, shape the response
services/    business logic, one responsibility per file (enhancement, stacking, storage, ...)
models/      Pydantic request/response models (the API contract)
db/          SQLAlchemy ORM models + session/engine management
utils/       shared helpers - image IO, linear ingest, math, validators, rate limiting
tasks/       Celery app + the task functions (thin wrappers over services/)
```

The one hard rule: **`routes/` may import `services/`; `services/` must never
import `routes/`.** A helper two features need lives in `utils/`. See
[AGENTS.md](../AGENTS.md) section 6.

## Request path: a single-image edit

```
POST /api/upload
  -> decode_image() normalises JPEG/PNG/TIFF/FITS/RAW/16-bit to a BGR uint8 array
  -> StorageService writes images/{session}/original.jpg, opens a SessionRecord

POST /api/process/{session}          (also: preset apply, Auto Astro)
  -> EnhancementService.dispatch()
       - retires ("superseded") any still-pending job for this session
       - checks the per-IP concurrency limit
       - creates a JobRecord
       - sync: runs inline  |  queue: task_process_image.delay(...)
  -> EnhancementService.run()
       - ImageProcessingService.apply_parameters() walks the pipeline
         (geometry -> sky/optics -> tone -> curves -> colour -> detail -> stars),
         calling on_step(name, percent) at each stage
       - each on_step updates the JobRecord and publishes a progress event
       - StorageService writes processed.jpg + preview.jpg; parameters are saved
         on the session

GET /api/preview/{session}?full=true  -> the current result (cache-busted by ?v=)
WS  /ws/processing-status/{job}       -> live progress until a terminal status
```

The editor re-runs `/process` on every slider change (500 ms debounced) against
the 512 px preview; the full-resolution render is produced on demand for
`?full=true` and for download.

## Request path: a stack

```
POST /api/stack/initiate               -> a StackRecord, status "waiting_for_frames"
POST /api/stack/{id}/upload-frames     -> linear_ingest.ingest_frame() per file:
                                          float32 [0,1], linear, CFA mosaic kept intact;
                                          stored at source bit depth under stacks/{id}/frames/
POST /api/stack/{id}/calibration/...   -> dark/flat/bias/dark_flat subs (optional)
POST /api/stack/{id}/process           -> StackingService.dispatch() -> a JobRecord
  -> StackingService.process()
       - CalibrationService builds (or loads cached) master frames
       - IntegrationService.integrate() runs three memory-bounded passes on a
         thread pool (stacking_workers):
           1. register  - calibrate + superpixel-debayer at half-res, detect stars,
                           score every frame, drop the quality rejects, pick the
                           reference, asterism-match the rest
           2. align     - reload, full-res edge-aware debayer, warp into the
                           reference, normalise, stream to a float16 memmap
           3. combine   - tile over the memmap: sigma-clip + winsorise + weighted mean
       - optional drizzle pass (drizzle_factor 2/3)
       - apply_post_stack() crops the field-rotation wedge, bakes it into composite.npy
       - a fresh SessionRecord is created and seeded with render_stack_base()
  -> the composite is now an ordinary session - enhance / preview / download it
     exactly like an upload; the editor gains a non-destructive "Stack" step
     (background extraction + colour calibration + stretch on the linear data)
```

After the align pass a checkpoint (`accum/plan.json` + the memmap) is written, so
a re-stack that only changes the combination / rejection / weighting / drizzle
resumes from the aligned frames (within ~30 min). Full detail:
[ALGORITHMS.md](ALGORITHMS.md#stacking).

## Progress over WebSockets

`app/services/progress.py` is the seam:

- **queue mode** - `run()` publishes each progress event to a Redis channel keyed
  by `job_id`; the WebSocket handler subscribes and relays until a terminal
  status, having first sent the current `JobRecord` from the DB as catch-up for a
  late subscriber.
- **sync mode** - the job is already terminal by the time the client can connect,
  so the handler just replays that final state and closes.

Either way the client sees the same message shape (see
[API.md](API.md#websocket-messages)).

## Database

SQLAlchemy ORM over **SQLite by default** (`DATA_DIR/db/myastroshine.db`, shared
between `api` and `worker` over the volume - fine for one worker and short
writes). Set `DATABASE_URL` to a Postgres URL before scaling the worker out.

Six tables (`app/db/models.py`):

| Table | Holds |
|-------|-------|
| `sessions` | one upload/edit session: working-file path, last-applied parameters, expiry |
| `jobs` | an async processing job: status, progress, current step, client IP |
| `presets` | a named `ProcessingParameters` set (5 built-ins + user presets) |
| `stacks` | a stacking session: frame count, settings, per-frame quality report, result stats |
| `astrodex_links` | ties a session to the AstroDex picture it was handed off from + the return-delivery status |
| `webhook_tokens` | webhook token (hash only) + its signing secret, for the AstroDex handoff |

**Migrations** live in `backend/migrations/` (Alembic). Apply them with
`alembic upgrade head` before starting a production instance. For local dev and
tests, `init_db()` also runs `create_all` (harmless alongside Alembic) and a
lightweight schema-drift check that reconciles a column a migration missed. See
[DEPLOYMENT.md](DEPLOYMENT.md#database-migrations).

## Storage layout

Everything hangs off `DATA_DIR` (`/data` in the container):

```
/data/
  db/myastroshine.db          SQLite database
  images/<session>/
    original.jpg              full-resolution upload
    processed.jpg             full-resolution latest result
    preview.jpg               downscaled result (fast display)
    depth/depth_map.png
    depth/layer_<n>.png       BGRA parallax layers, far (0) to near
  stacks/<stack>/
    frames/<00000..>.npy      ingested linear frames (source bit depth)
    calibration/<kind>/       dark / flat / bias / dark_flat subs + cached masters
    thumbs/                   ~256 px frame-grid thumbnails
    accum/                    align checkpoint (plan.json + the float16 memmap)
    composite.npy             the 32-bit linear composite
  cache/                      server-side caches
  secret_key.txt              generated once (0600) - session signing + HMAC fallback
  app_settings.json           runtime settings edited in the UI
  myastroshine.log            rotating API log (10 MB x 5)
  worker.log                  rotating worker log
  celerybeat-schedule         beat's persisted schedule state
```

Back up the whole volume. Session images are transient and pruned after
`session_expiry_hours`; a stack's frames are kept `stacking_retention_hours`.

## Background schedule

The `worker` runs Celery beat in-process (`-B`). Hourly:

- `task_cleanup_sessions` - deletes expired sessions and stacks (and their
  files), fails jobs left stuck by a crash, and prunes finished job rows past
  `job_history_retention_hours` (the admin Settings -> Operations job-history
  view, otherwise unbounded - every debounced slider edit inserts a row).
  Runs regardless of `PROCESSING_MODE` (drop the worker and you lose this).
- `task_watch_stacking_folder` - a no-op unless `stacking_watch_dir` is set; when
  it is, it ingests new frames dropped into that folder and (optionally)
  auto-stacks once the folder goes idle.

Beat only runs correctly at **one** worker replica. Move it to its own service
before scaling the worker out.

## Frontend

React 19 + TypeScript + Vite + Tailwind v4 (configured CSS-first in
`src/styles/index.css`, no `tailwind.config.js`). Minimal hash routing
(`#/settings`), no router dependency.

- **`App.tsx`** is the orchestrator: a single-image editor, a stacking view, and
  a Settings screen. It reads a `?handoff=` token on load to detect an AstroDex
  hand-off and resume straight into the editor.
- **`components/`** are function components with typed props; **`hooks/`** own
  state and side effects (`useImageProcessing`, `useStackProcessing`,
  `useDepthShift`, ...); **`services/`** are the API and WebSocket clients.
- All frontend types are **camelCase**. The backend speaks snake_case;
  conversion happens *only* in `services/api.ts` / `ws.ts` via `caseConvert.ts`.
- UI text is translated (FR + EN, `src/i18n/translations/*.json`) and read with
  `useTranslation()`'s `t()` - never hardcoded.

See [DESIGN.md](DESIGN.md) for the visual system.

## AstroDex integration

Optional, and off unless configured. MyAstroBoard opens MyAstroShine with a
single signed **handoff token** in the URL; this instance is never called *by*
the board, only ever calls *out* to it, so the flow survives the board being
behind a reverse proxy.

- **Resume** - `POST /api/astrodex/handoff/resume` verifies the token (its `kid`
  picks the webhook token whose `signing_secret` signs it), checks
  `callback_base` against the `astrodex_callback_urls` allowlist, then pulls the
  source image + metadata from the board and opens a session.
- **Return** - `POST /api/astrodex/handoff/return` posts the processed image
  back as a signed `multipart/form-data` request; the board files it as a **new**
  picture on the same object (never a replacement). Retried with backoff.

The allowlist fails closed (empty = every URL refused) - the main SSRF guard.
Contract detail: [API.md](API.md#astrodex-integration). Full design:
`initial_plan/PASSATION_MYASTROBOARD_INTEGRATION.md`.
