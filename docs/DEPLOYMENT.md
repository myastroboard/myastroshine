# Deployment and configuration

## Philosophy

`docker compose up` works with **no `.env` editing**. The compose file carries
only *structural* variables - the run mode, the persistence root, the container
topology. Everything a user might tune (CORS origins, the AstroDex callback
allowlist, upload limits, session lifetime, stacking defaults, log levels) is
edited from **Settings** in the UI and persisted under the data volume. The
session secret is generated on first start.

## Services

`docker-compose.yml` defines three services on the `myastroshine` network. A
single image (FastAPI + OpenCV, serving the built React UI alongside the API)
backs both `api` and `worker`:

| Service | Image / build | Port | Volumes |
|---------|---------------|------|---------|
| `api` | `.` (API + web UI) | 8002 | `myastroshine_data:/data` |
| `worker` | `.` (Celery worker + embedded beat, `target: backend`) | - | `myastroshine_data:/data` |
| `redis` | `redis:7-alpine` | 6379 | `myastroshine_redis:/data` |

This stack sets `PROCESSING_MODE=queue`, so `/api/process` and
`/api/stack/{id}/process` enqueue a Celery task the `worker` runs, and progress
streams over `/ws/processing-status/{job_id}` (or `/ws/stack-status/{id}`). Set
`PROCESSING_MODE=sync` to run everything inside the request instead - `worker`
and `redis` are then optional for processing, but dropping `worker` also drops
the beat-scheduled session cleanup below; keep it running if you want that.

> SQLite is shared between `api` and `worker` over the volume. This is fine for a
> single worker and short writes; set `DATABASE_URL` to a Postgres URL before
> scaling the worker out.

`worker` also runs Celery beat in-process (`-B`), which hourly runs
`task_cleanup_sessions` - deletes sessions past `session_expiry_hours` (and
their files) regardless of `PROCESSING_MODE`. Its schedule state lives at
`DATA_DIR/celerybeat-schedule`. Beat only ever runs once as long as `worker`
stays at one replica; scaling it out would run the schedule multiple times, so
move beat to its own service first if you ever do that.

## Clean-machine quick start (no repo clone)

Every tagged release publishes one image - `ghcr.io/myastroboard/myastroshine`
(also mirrored to Docker Hub as `myastroboard/myastroshine`) - covering both
the API and the web UI. If you just want to run MyAstroShine and don't need
the source, grab `docker-compose.yml` on its own and start it - `docker
compose up -d` pulls the published image by default (`api`'s `image:` line),
it does not need `build:` or a local Dockerfile:

```bash
curl -O https://raw.githubusercontent.com/myastroboard/myastroshine/main/docker-compose.yml
docker compose up -d

curl http://localhost:8002/api/health
open http://localhost:8002
```

Pin a specific release instead of `latest`:

```bash
MYASTROSHINE_VERSION=0.1.0 docker compose up -d
```

Cloned the repo instead? `docker compose up -d --build` (or `docker compose
build` first) builds from the local `Dockerfile`, ignoring the published
image - see the main [Quick start](../README.md#quick-start-docker).

## The data volume

Everything the app persists hangs off one root, `DATA_DIR` (`/data` in the
container):

```
/data/
  db/myastroshine.db      SQLite database
  images/<session>/       per-session working files
  stacks/<stack>/         stacking frames (v1.1+)
  cache/                  server-side caches
  secret_key.txt          auto-generated once; HMAC fallback + session signing
  app_settings.json       runtime settings edited in the UI
  myastroshine.log        rotating application log
```

Back up this volume. Session images are transient and pruned after the
configured session lifetime.

## Structural environment variables

Set only to change the deployment shape (see `backend/.env.example`):

| Variable | Default | Notes |
|----------|---------|-------|
| `APP_ENV` | `development` | `development` renders logs for humans; `production` emits JSON |
| `DATA_DIR` | `./data` (local), `/data` (image) | the single persistence root |
| `PROCESSING_MODE` | `sync` | `sync` or `queue` (compose sets `queue`) |
| `REDIS_URL` / `CELERY_BROKER_URL` | `redis://localhost:6379/0` `/1` | only used with `queue`; compose points them at the `redis` service |
| `DATABASE_URL` | *(derived)* | set to a Postgres URL to override the SQLite default |
| `ADMIN_ENABLED` | `true` | set `false` to make `/api/admin/*` reject writes |

## Runtime settings (edited in the UI)

**Settings** in the app writes `DATA_DIR/app_settings.json` via
`POST /api/admin/app-settings` and the change takes effect immediately (except
`cors_origins`, which the CORS middleware reads once at startup - restart `api`
after changing it).

| Tab | Setting | Default |
|-----|---------|---------|
| General | `max_image_size_mb` | 100 |
| General | `session_expiry_hours` | 24 |
| General | `preview_max_size` | 512 |
| General | `stacking_enabled` / `stacking_max_frames` / `stacking_detector` / `stacking_combination_default` / `stacking_cosmic_ray_threshold` | see `app/utils/app_settings.py` |
| Webhooks | AstroDex bearer tokens (create / revoke) | - |
| Webhooks | `astrodex_callback_urls` (allowlist) | empty |
| Webhooks | `astrodex_max_retries` / `astrodex_retry_delay_seconds` | 3 / 5s |
| Advanced | `cors_origins` | `http://localhost:3000` |
| Advanced | `rate_limit_enabled` / `rate_limit_per_minute` / `max_concurrent_jobs_per_ip` | `true` / 120 / 5 |
| Advanced | `log_level` / `console_log_level` | `info` / `warning` |

## Frontend environment

Frontend (`frontend/.env`, see `frontend/.env.example`):

| Variable | Default | Notes |
|----------|---------|-------|
| `VITE_API_URL` | `/api` | absolute only when the API is on another origin |
| `VITE_WS_URL` | `/ws` on the page origin | as above |
| `VITE_PROXY_TARGET` | `http://localhost:8002` | dev-server only: where `/api` + `/ws` proxy (the dev compose sets `http://api:8002`) |
| `VITE_APP_NAME` | `MyAstroShine` | |
| `VITE_APP_VERSION` | resolved automatically | see `vite.config.ts`; only set this to override |

Leave `VITE_API_URL` / `VITE_WS_URL` unset unless the backend really is on a
different origin: the app then uses same-origin `/api` and `/ws`. In
production the API *is* the same origin (one image serves both), so there's
nothing to proxy; in dev the Vite dev server (via `VITE_PROXY_TARGET`) proxies
both to the API. Setting an absolute `VITE_API_URL` makes `fetch` bypass that
proxy while `<img src="/api/...">` does not, which breaks image loads in dev.

## Startup (production-like)

```bash
docker compose build
docker compose up -d

curl http://localhost:8002/api/health
```

## Development stack (hot reload)

`docker-compose.dev.yml` runs the API under `uvicorn --reload` and the frontend
under the Vite dev server, both with the source bind-mounted:

```bash
docker compose -f docker-compose.dev.yml up
# API   http://localhost:8002/api/health   (restarts on backend edits)
# web   http://localhost:3000               (HMR on frontend edits)
```

Data and the SQLite database land in `./data` on the host. File watching uses
polling (`VITE_USE_POLLING=1`) so edits are picked up on Windows and macOS.

## Database migrations

Alembic is configured in `backend/alembic.ini` / `backend/migrations/`. The URL
comes from application settings at runtime (`DATABASE_URL`, or the derived SQLite
path under `DATA_DIR`). The initial revision
(`606a1e113989_create_core_tables.py`) covers all six tables.

Apply migrations before starting a production instance:

```bash
cd backend
alembic upgrade head
```

When the models change, author a new revision and check its diff before
committing it:

```bash
cd backend
alembic revision --autogenerate -m "describe the change"
alembic upgrade head   # apply it locally and eyeball the generated SQL
```

For local development and tests, `init_db()` calls `Base.metadata.create_all`
as a convenience (it only creates tables that don't exist yet, so it is
harmless to run alongside Alembic); production should rely on
`alembic upgrade head`. `api` and `worker` share the same SQLite file under
`DATA_DIR`, so migrations are applied manually and once, not from either
container's entrypoint.

## Logs

- The API writes `DATA_DIR/myastroshine.log`, the worker `DATA_DIR/worker.log` -
  both rotating (10 MB x 5). The console (`docker compose logs api`) carries the
  same events at `console_log_level`.
- Timestamps are in the `TZ` zone with the UTC offset always shown.
- **Settings -> Logs** tails the file, changes filter level, clears it, and
  exports a ZIP of the log plus its rotations and the worker log - attach that
  ZIP to bug reports. `log_level` / `console_log_level` are on the Advanced tab
  and apply without a restart.
- CLI equivalents: `GET/POST /api/admin/logs*` (see `docs/API.md`).

## Backup

Back up the `myastroshine_data` volume regularly - it holds the database, the
settings file, and the session secret. `myastroshine_redis` is a transient
broker and does not need backing up.

## Reverse proxy

The `api` container serves the web UI, the API, and the WebSocket endpoints
directly on :8002 - there's no internal proxy to configure. For anything
beyond localhost, place Caddy or nginx in front of it for TLS (application-
level rate limiting is already in place, see `docs/API.md` "Rate Limiting").

## Health checks

The `api` container has a Docker healthcheck hitting `/api/health`. Check status
with `docker compose ps`.
