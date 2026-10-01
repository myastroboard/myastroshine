# MyAstroShine - single image: FastAPI (+OpenCV) API, serving the built React
# SPA alongside it. Build context is the repo root.
#
#   docker build --target backend-with-frontend -t myastroshine .   # default
#   docker build --target backend -t myastroshine-backend-only .    # dev (no SPA)
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
# Stage: python-wheels - every runtime dependency as a wheel, with the ones that
# need it rebuilt for older x86-64 CPUs. Only the wheels reach the image: the
# compiler stays here.
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS python-wheels

ARG TARGETARCH
# PyPI's NumPy wheels need x86-64-v2 (SSE4.2/POPCNT) and die with SIGILL on an
# older CPU model such as Proxmox "kvm64", the default of the Home Assistant OS VM
# scripts. On amd64, rebuild them with no CPU baseline: NumPy still picks its
# SSE4 / AVX2 / AVX-512 kernels at run time on CPUs that have them.
# scripts/check_cpu_compat.sh proves the result; CONTRIBUTING.md "CPU compatibility".
ARG REBUILD_FOR_OLD_CPUS="numpy"

RUN apt-get update && apt-get install -y --no-install-recommends gcc g++     && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt
# --no-cache-dir matters: pip's wheel cache ignores the -C build settings and
# would silently hand back a wheel built with the default baseline.
RUN if [ "$TARGETARCH" = "amd64" ]; then       set -e;       for pkg in $REBUILD_FOR_OLD_CPUS; do         version=$(sed -n "s/^${pkg}==//Ip" requirements.txt);         [ -n "$version" ] || { echo "$pkg: no '${pkg}==' pin in requirements.txt"; exit 1; };         wheel_name=$(echo "$pkg" | tr 'A-Z.-' 'a-z__');         find /wheels -iname "${wheel_name}-*.whl" -delete;         extra="";         if [ "$pkg" = "numpy" ]; then           extra="-Csetup-args=-Dcpu-baseline=none -Csetup-args=-Dallow-noblas=true";         fi;         pip wheel --no-cache-dir --no-binary "$pkg" --no-deps --wheel-dir /wheels           "${pkg}==${version}" $extra;       done;     fi

# ---------------------------------------------------------------------------
# Stage: backend - the API runtime, no static assets. This is the target
# docker-compose.dev.yml builds (Vite's dev server serves the frontend live in
# dev, so it does not need the frontend-builder stage above).
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
RUN --mount=type=bind,from=python-wheels,source=/wheels,target=/wheels     pip install --no-cache-dir --no-index --find-links /wheels -r requirements.txt

COPY backend/app/ app/
COPY backend/alembic.ini .
COPY backend/migrations/ migrations/

# Single persistence root; the app creates the subtree (db/, images/, stacks/,
# cache/) and secret_key.txt / app_settings.json at startup.
ENV DATA_DIR=/data
RUN mkdir -p /data

# Mount point for optional operator-installed ML engines (StarNet2 / DeepSNR).
# Nothing is bundled: the compose files bind-mount ./engines here read-only and
# the operator drops the binary in. Empty and inert unless a path is set in
# Settings. See docs/DEPLOYMENT.md "External ML engines" and THIRD_PARTY.md.
RUN mkdir -p /opt/engines

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8002/api/health || exit 1

# Dual-stack (IPv4 + IPv6) listener with a bounded graceful shutdown - see app/serve.py.
CMD ["python", "-m", "app.serve"]

# ---------------------------------------------------------------------------
# Stage: backend-with-frontend - the published image. Adds the built SPA;
# app/main.py mounts it at "/" (StaticFiles) once this directory exists.
# ---------------------------------------------------------------------------
FROM backend AS backend-with-frontend

COPY --from=frontend-builder /app/frontend/dist ./static
