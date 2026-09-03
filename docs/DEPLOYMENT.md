# Deployment and configuration

## Services

`docker-compose.yml` defines three services on the `myastroshine` network:

| Service | Image / build | Port | Volumes |
|---------|---------------|------|---------|
| `api` | `./backend` (FastAPI + OpenCV) | 8002 | `myastroshine_images:/data/images`, `myastroshine_db:/data/db` |
| `web` | `./frontend` (Vite build served by nginx) | 3000 | - |
| `redis` | `redis:7-alpine` | 6379 | `myastroshine_redis:/data` |

Redis is only used from phase 2+ (Celery job queue). It is safe to leave running
before then.

## Environment variables

Backend (`backend/.env`, see `backend/.env.example`):

| Variable | Default | Notes |
|----------|---------|-------|
| `APP_ENV` | `development` | `development` enables console log rendering |
| `DEBUG` | `true` | |
| `LOG_LEVEL` | `info` | `debug` / `info` / `warning` / `error` |
| `DATABASE_URL` | `sqlite:///./data/db/myastroshine.db` | SQLAlchemy URL |
| `STORAGE_PATH` | `./data/images` | session working files |
| `MAX_IMAGE_SIZE_MB` | `100` | upload limit |
| `SESSION_EXPIRY_HOURS` | `24` | cleanup window |
| `API_CORS_ORIGINS` | `http://localhost:3000,...` | comma-separated |
| `ASTRODEX_WEBHOOK_SECRET` | `change-me` | HMAC shared secret |
| `ASTRODEX_CALLBACK_URLS` | - | comma-separated allowlist |
| `ASTRODEX_MAX_RETRIES` | `3` | webhook retries |
| `REDIS_URL` / `CELERY_BROKER_URL` | `redis://localhost:6379/0` / `/1` | phase 2+ |
| `DEPTH_DETECTION_METHOD` | `gradient` | `gradient` or `ml` |
| `STACKING_*` | see `.env.example` | v1.1+ |

Frontend (`frontend/.env`, see `frontend/.env.example`):

| Variable | Default |
|----------|---------|
| `VITE_API_URL` | `http://localhost:8002/api` |
| `VITE_WS_URL` | `ws://localhost:8002/ws` |
| `VITE_APP_NAME` | `MyAstroShine` |
| `VITE_APP_VERSION` | `0.1.0` |

## Startup (production-like)

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

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
comes from application settings at runtime.

```bash
cd backend
alembic revision --autogenerate -m "create core tables"
alembic upgrade head
```

For local development and tests, `init_db()` calls `Base.metadata.create_all`
as a convenience; production should rely on `alembic upgrade head`.

## Persistence and backup

Volumes: `myastroshine_images`, `myastroshine_db`, `myastroshine_redis`. Back up
the DB volume regularly; session images are transient and pruned after
`SESSION_EXPIRY_HOURS`.

## Reverse proxy

The `web` container already proxies `/api/` and `/ws/` to `api:8002` (see
`frontend/nginx.conf`). For production place Caddy or nginx in front for TLS and
rate limiting (`/api/* 10r/m` planned for v1.5+).

## Health checks

The `api` container has a Docker healthcheck hitting `/api/health`. Check status
with `docker compose ps`.
