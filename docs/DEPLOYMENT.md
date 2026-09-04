# Deployment and configuration

## Philosophy

`docker compose up` works with **no `.env` editing**. The compose file carries
only *structural* variables - the run mode, the persistence root, the container
topology. Everything a user might tune (CORS origins, the AstroDex callback
allowlist, upload limits, session lifetime, stacking defaults, log levels) is
edited from **Settings** in the UI and persisted under the data volume. The
session secret is generated on first start.

## Services

`docker-compose.yml` defines four services on the `myastroshine` network:

| Service | Image / build | Port | Volumes |
|---------|---------------|------|---------|
| `api` | `./backend` (FastAPI + OpenCV) | 8002 | `myastroshine_data:/data` |
| `worker` | `./backend` (Celery worker) | - | `myastroshine_data:/data` |
| `web` | `./frontend` (Vite build served by nginx) | 3000 | - |
| `redis` | `redis:7-alpine` | 6379 | `myastroshine_redis:/data` |

This stack sets `PROCESSING_MODE=queue`, so `/api/process` and
`/api/stack/{id}/process` enqueue a Celery task the `worker` runs, and progress
streams over `/ws/processing-status/{job_id}` (or `/ws/stack-status/{id}`). Set
`PROCESSING_MODE=sync` to run everything inside the request instead - then the
`worker` and `redis` services are optional.

> SQLite is shared between `api` and `worker` over the volume. This is fine for a
> single worker and short writes; set `DATABASE_URL` to a Postgres URL before
> scaling the worker out.

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
| `DEBUG` | `true` | |
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
| General | `denoise_enable_ml` | false |
| General | `depth_detection_method` | `gradient` |
| General | `stacking_enabled` / `stacking_max_frames` / `stacking_detector` / `stacking_combination_default` / `stacking_cosmic_ray_threshold` | see `app/utils/app_settings.py` |
| Webhooks | AstroDex bearer tokens (create / revoke) | - |
| Webhooks | `astrodex_callback_urls` (allowlist) | empty |
| Webhooks | `astrodex_max_retries` / `astrodex_retry_delay_seconds` | 3 / 5s |
| Advanced | `cors_origins` | `http://localhost:3000` |
| Advanced | `log_level` / `console_log_level` | `info` / `warning` |

## Frontend environment

Frontend (`frontend/.env`, see `frontend/.env.example`):

| Variable | Default | Notes |
|----------|---------|-------|
| `VITE_API_URL` | `/api` | absolute only when the API is on another origin |
| `VITE_WS_URL` | `/ws` on the page origin | as above |
| `VITE_PROXY_TARGET` | `http://localhost:8002` | dev-server only: where `/api` + `/ws` proxy (the dev compose sets `http://api:8002`) |
| `VITE_APP_NAME` | `MyAstroShine` | |
| `VITE_APP_VERSION` | `0.1.0` | |

Leave `VITE_API_URL` / `VITE_WS_URL` unset unless the backend really is on a
different origin: the app then uses same-origin `/api` and `/ws`, which the dev
server (via `VITE_PROXY_TARGET`) and the production nginx both proxy to the API.
Setting an absolute `VITE_API_URL` makes `fetch` bypass that proxy while
`<img src="/api/...">` does not, which breaks image loads in Docker.

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
path under `DATA_DIR`).

```bash
cd backend
alembic revision --autogenerate -m "create core tables"
alembic upgrade head
```

For local development and tests, `init_db()` calls `Base.metadata.create_all`
as a convenience; production should rely on `alembic upgrade head`.

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

The `web` container already proxies `/api/` and `/ws/` to `api:8002` (see
`frontend/nginx.conf`). For production place Caddy or nginx in front for TLS and
rate limiting (`/api/* 10r/m` planned for v1.5+).

## Health checks

The `api` container has a Docker healthcheck hitting `/api/health`. Check status
with `docker compose ps`.
