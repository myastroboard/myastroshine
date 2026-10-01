# Deployment and configuration

## Contents

- [Philosophy](#philosophy)
- [Services](#services)
- [Clean-machine quick start (no repo clone)](#clean-machine-quick-start-no-repo-clone)
- [The data volume](#the-data-volume)
- [Structural environment variables](#structural-environment-variables)
- [Runtime settings (edited in the UI)](#runtime-settings-edited-in-the-ui)
- [External ML engines (optional)](#external-ml-engines-optional)
- [Frontend environment](#frontend-environment)
- [Development stack (hot reload)](#development-stack-hot-reload)
- [Database migrations](#database-migrations)
- [Logs](#logs)
- [Backup](#backup)
- [Reverse proxy](#reverse-proxy)
- [Health checks](#health-checks)

The runtime topology is in [ARCHITECTURE.md](ARCHITECTURE.md).

## Philosophy

`docker compose up` works with **no `.env` editing**. The compose file carries
only *structural* variables - the run mode, the persistence root, the container
topology. Everything a user might tune (CORS origins, the Astrodex callback
allowlist, upload limits, session lifetime, stacking defaults, log levels) is
edited from **Settings** in the UI and persisted under the data volume. The
session secret is generated on first start.

## Services

`docker-compose.yml` defines **one** service, `api`, on the `myastroshine`
network - a single image (FastAPI + OpenCV, serving the built React UI alongside
the API):

| Service | Image / build | Port | Volumes |
|---------|---------------|------|---------|
| `api` | `.` (API + web UI + background jobs) | 8002 | `myastroshine_data:/data`, `./engines:/opt/engines:ro` |

Image and stack processing run as background jobs inside that process:
`/api/process` and `/api/stack/{id}/process` answer at once with a `queued` job
and progress streams over `/ws/processing-status/{job_id}` (or
`/ws/stack-status/{id}`). The same process runs the maintenance: an hourly
cleanup (expired sessions and stacks, stuck jobs, old job history, expired admin
logins) and the minute-by-minute watch-folder poll. See
[ARCHITECTURE.md](ARCHITECTURE.md#background-jobs).

**Upgrading from a version with `worker` and `redis` services** (0.4.x and
earlier): use the new `docker-compose.yml`, or delete the `worker` and `redis`
services and the `PROCESSING_MODE` / `REDIS_URL` / `CELERY_BROKER_URL`
variables from yours. The `myastroshine_data` volume is unchanged; the
`myastroshine_redis` volume and any `worker.log` / `celerybeat-schedule` files
in the data volume can be deleted. Leftover variables are ignored.

## Clean-machine quick start (no repo clone)

Every tagged release publishes one image to both `myastroboard/myastroshine`
(Docker Hub - what `docker-compose.yml` pulls) and its mirror
`ghcr.io/myastroboard/myastroshine` - covering both the API and the web UI. If you just want to run MyAstroShine and don't need
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
  images/<session>/       per-session working files (original / processed / preview / depth layers)
  stacks/<stack>/         stacking frames, calibration subs, thumbnails, align checkpoint, composite.npy
  cache/                  server-side caches
  secret_key.txt          auto-generated once (0600); HMAC fallback + session signing
  app_settings.json       runtime settings edited in the UI
  myastroshine.log        rotating application log (10 MB x 5)
```

Back up this volume. Session images are transient and pruned after
`session_expiry_hours`; a stack's frames are kept `stacking_retention_hours`.
Full layout: [ARCHITECTURE.md](ARCHITECTURE.md#storage-layout).

## Structural environment variables

Set only to change the deployment shape (see `backend/.env.example`):

| Variable | Default | Notes |
|----------|---------|-------|
| `APP_ENV` | `development` | `development` renders logs for humans; `production` emits JSON |
| `DATA_DIR` | `./data` (local), `/data` (image) | the single persistence root |
| `DATABASE_URL` | *(derived)* | another database URL to override the SQLite default |
| `ADMIN_ENABLED` | `true` | set `false` to turn the administration surface (`/api/admin/*`, `/api/tokens`, admin login) off entirely |

## Admin password

Settings (and every `/api/admin/*` / `/api/tokens` route) is reserved for the
administrator. On a fresh install - or the first start after upgrading from a
version without it - the Settings page asks you to **create the admin
password** (10 characters minimum); until then the administration surface is
locked. Using the app itself (upload, edit, stack, download) never asks for it.

Change the password, see the browsers logged in as admin, and set how long a
login lasts under **Settings -> Security**.

Lost the password? Reset it from the host - it forgets the password and every
admin login, and the next visit to Settings asks for a new one:

```bash
docker exec myastroshine-api python -m app.cli reset-admin
```

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
| Stacking | `stacking_enabled` / `stacking_max_frames` / `stacking_retention_hours` | true / 2000 / 12 |
| Stacking | `stacking_workers` (register/align/combine threads; 0 = auto, cap 4) | 0 |
| Stacking | `stacking_watch_dir` / `stacking_watch_idle_minutes` / `stacking_watch_auto_process` (folder-watch ingest; empty dir = off) | "" / 10 / true |
| Astrodex | webhook token (create / revoke; paste token + signing secret into MyAstroBoard) | - |
| Astrodex | `astrodex_callback_urls` (board-origin allowlist, fails closed) | empty |
| Astrodex | `astrodex_max_retries` / `astrodex_retry_delay_seconds` (return delivery) | 3 / 5s |
| ML engines | StarNet2 / DeepSNR package (install from its archive, or remove) | - |
| ML engines | `starnet2_path` / `deepsnr_path` / `starnet2_stride` / `deepsnr_stride` (empty = off) | "" / "" / 0 / 0 |
| Security | admin password, logged-in browsers, `admin_session_idle_days` | - / - / 7 |
| Security | `cors_origins` | `http://localhost:3000` |
| Security | `rate_limit_enabled` / `rate_limit_per_minute` / `max_concurrent_jobs_per_ip` | `true` / 600 / 5 |
| Logs | `log_level` / `console_log_level` | `info` / `warning` |
| Maintenance | `job_history_retention_hours` (how long a finished job row is kept before the hourly cleanup prunes it) | 168 (7 days) |

## External ML engines (optional)

Star removal can run through [StarNet2](https://starnetastro.com/) and denoise
through DeepSNR instead of the built-in classical code. **MyAstroShine bundles
neither** - see `THIRD_PARTY.md`. The operator installs the binary and MyAstroShine
shells out to it; with no path set, the classical engines are the only option and
nothing changes.

**Install from Settings (simplest).** Download the CLI package for
**linux-x64** from `starnetastro.com` (there is no linux-arm64 build - an ARM
host cannot use it, and the upload says so), then in **Settings -> ML engines** click **Install StarNet2 from its archive** (or DeepSNR)
and pick the `.zip` / `.tar.gz` as downloaded. The server unpacks and checks it
(the binary for this machine's architecture, its weights, its licence) and runs
`--version`; Settings then shows the package's own `LICENSE.txt`. Tick that you
downloaded it yourself and accept it, click **Install**: the package lands in
`DATA_DIR/engines/<engine>/` and its path is set for you. **Remove** deletes it.
Up to 1 GiB per archive. Admin only - installing an engine runs a binary on the
server.

**Or mount it yourself.** The `./engines` directory next to the compose file is
**already bind-mounted read-only into `api`** at `/opt/engines` (empty and inert
until you set a path). Its contents are git-ignored.

1. Download the CLI build for **linux-x64** from `starnetastro.com`. Read its
   bundled `LICENSE.txt` - it grants use "solely for astrophotography image
   processing"; the model is non-commercial, so a monetised instance takes that
   clause on.
2. Unpack it into `./engines/`, e.g. `./engines/starnet2/starnet2` and/or
   `./engines/deepsnr/deepsnr`, then `docker compose up -d`. (Running the
   published image without the repo? Create an `engines/` dir next to your
   `docker-compose.yml` first.) The image runs on Debian 13 / glibc 2.41, which
   meets the tools' runtime baseline.
3. In **Settings -> ML engines**, set `starnet2_path` /
   `deepsnr_path` to the path inside the container (e.g.
   `/opt/engines/starnet2/starnet2`), Save, then **Re-check engines**. A green
   "detected" line means the editor now offers that engine: a "StarNet2" toggle
   in the **Stars** step, a "DeepSNR" toggle in the **Detail** step's denoise
   control.

The probe result is cached until the next settings save. Tested against StarNet2
**2.6.1** / DeepSNR **1.3.1**; a version outside `2.6.x` / `1.3.x` still runs,
with an amber "untested" warning. A pass streams progress to the editor's bar; on
failure or timeout (15 min) the pipeline falls back to the classical code.

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
path under `DATA_DIR`). `606a1e113989_create_core_tables` creates the six tables;
later revisions add the stacking columns, per-frame quality, calibration,
drizzle, folder-watch, and the job client IP.

`init_db()` runs on API startup and brings the schema to Alembic
`head` automatically:

- a brand-new database is built entirely from the migrations;
- a legacy database from an earlier `create_all` (no `alembic_version` table) is
  filled in and stamped at `head`;
- a lightweight **schema-drift check** then compares the ORM columns against the
  live schema. On SQLite it adds any column a migration missed, in place (and
  logs an error so the migration still gets fixed); on Postgres it raises -
  migrations must be correct there, and `tests/db/test_migrations.py` keeps them
  that way.

For a Postgres deployment, apply migrations explicitly before starting:

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


## Logs

- The app writes `DATA_DIR/myastroshine.log`, rotating (10 MB x 5). The console (`docker compose logs api`) carries the
  same events at `console_log_level`.
- Timestamps are in the `TZ` zone with the UTC offset always shown.
- **Settings -> Logs** tails the file, changes filter level, clears it, and
  exports a ZIP of the log plus its rotations - attach that
  ZIP to bug reports. `log_level` / `console_log_level` are at the top of the
  same Logs screen and apply without a restart.
- CLI equivalents: `GET/POST /api/admin/logs*` (see `docs/API.md`).

## Backup

Back up the `myastroshine_data` volume regularly - it holds the database, the
settings file, and the session secret.

## Reverse proxy

The `api` container serves the web UI, the API, and the WebSocket endpoints
directly on :8002 - there's no internal proxy to configure. For anything
beyond localhost, place Caddy or nginx in front of it for TLS (application-
level rate limiting is already in place, see `docs/API.md` "Rate Limiting").

The app also works **under a path prefix** (`https://example.com/astro/`, or a
Home Assistant ingress): every URL the web UI builds - assets, API calls, images,
WebSockets - is relative to the page. The proxy must strip the prefix before
forwarding (`location /astro/ { proxy_pass http://myastroshine:8002/; }` with the
trailing slashes), forward WebSocket upgrades on `/ws/`, and pass the browser's
host in `X-Forwarded-Host` (the admin routes compare it with the request's
`Origin`).

## Health checks

The `api` container has a Docker healthcheck hitting `/api/health`. Check status
with `docker compose ps`.
