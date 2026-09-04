# MyAstroShine - single image: FastAPI (+OpenCV) API, serving the built React
# SPA alongside it. Build context is the repo root.
#
#   docker build --target backend-with-frontend -t myastroshine .   # default
#   docker build --target backend -t myastroshine-backend-only .    # worker / dev
#
# Version is baked in via build args (see app/__init__.py, vite.config.ts) -
# the release workflow passes --build-arg {APP,VITE_APP}_VERSION=$(cat VERSION).

# ---------------------------------------------------------------------------
# Stage: frontend-builder - only pulled in by the backend-with-frontend target
# ---------------------------------------------------------------------------
FROM node:26-alpine AS frontend-builder

ARG VITE_APP_VERSION=0.0.0-dev
ENV VITE_APP_VERSION=${VITE_APP_VERSION}

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ .
RUN npm run build

# ---------------------------------------------------------------------------
# Stage: backend - the api/worker runtime, no static assets. This is the
# target docker-compose.dev.yml and the worker service build (Vite's dev
# server serves the frontend live in dev; worker never serves HTTP at all -
# neither needs the frontend-builder stage above to run).
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS backend

ARG APP_VERSION=0.0.0-dev
ENV APP_VERSION=${APP_VERSION}

WORKDIR /app

# System dependencies for OpenCV runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app/ app/
COPY backend/alembic.ini .
COPY backend/migrations/ migrations/

# Single persistence root; the app creates the subtree (db/, images/, stacks/,
# cache/) and secret_key.txt / app_settings.json at startup.
ENV DATA_DIR=/data
RUN mkdir -p /data

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8002/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]

# ---------------------------------------------------------------------------
# Stage: backend-with-frontend - the published image. Adds the built SPA;
# app/main.py mounts it at "/" (StaticFiles) once this directory exists.
# ---------------------------------------------------------------------------
FROM backend AS backend-with-frontend

COPY --from=frontend-builder /app/frontend/dist ./static
