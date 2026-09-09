# MyAstroShine

[![GitHub Release](https://img.shields.io/github/v/release/myastroboard/myastroshine)](https://github.com/myastroboard/myastroshine/releases)
[![CI](https://github.com/myastroboard/myastroshine/actions/workflows/ci.yml/badge.svg)](https://github.com/myastroboard/myastroshine/actions/workflows/ci.yml)
[![astropy](https://img.shields.io/badge/powered%20by-AstroPy-orange.svg?style=flat)](https://www.astropy.org/)
[![Docker Pulls](https://img.shields.io/docker/pulls/myastroboard/myastroshine)](https://hub.docker.com/r/myastroboard/myastroshine)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0--or--later-blue.svg)](LICENSE)

**A self-hosted astronomical image processing tool: automatic enhancement,
multi-image stacking, and a parallax depth effect - from one Docker image, with
no account and no cloud upload.** It integrates optionally with
[MyAstroBoard](https://github.com/myastroboard/myastroboard)'s AstroDex, and runs
just as well standalone.

> **Status: Alpha.** `v0.2.0` is tagged and published to `ghcr.io` and Docker
> Hub. The full feature set is implemented and the frontend is wired end to end,
> but the code has not been through a production shakedown - expect breaking
> changes to the API, storage layout, and settings between releases, and don't
> rely on it for irreplaceable data. Current open items are in the
> [changelog](CHANGELOG.md#unreleased).

## Contents

- [What it does](#what-it-does)
- [Quick start (Docker)](#quick-start-docker)
- [Local development](#local-development)
- [Documentation](#documentation)
- [Technology](#technology)
- [Contributing](#contributing)
- [About](#about)

## What it does

- **Automatic enhancement** - a workflow-ordered editor: framing, background
  corrections (white balance, vignette, light-pollution gradient, dehaze), tone,
  master + per-channel **curves**, colour, detail (clarity, luma / colour
  denoise, sharpen).
- **One-click Auto Astro** - analyses the histogram and star density and applies
  an adaptive starting point. Plus five built-in **presets** and your own.
- **Star handling** - shrink stars in place, or lift them out entirely (starless
  workflow) and screen-blend them back at the end.
- **Geometry** - rotate, flip, straighten, crop, before the pixel pipeline runs.
- **Depth Shift** - a multi-layer parallax effect that gives a single frame a
  sense of 3D depth, with a pickable focal point.
- **Stacking** - align and combine 2-2000 linear frames: master dark / flat /
  bias calibration, per-frame quality scoring and auto-reject, asterism-matching
  registration, sigma-clipped weighted combination, optional drizzle - all in
  bounded memory, plus a folder-watch mode for a live capture rig.
- **Optional ML engines** - point it at an operator-installed
  [StarNet2](https://starnetastro.com/) / DeepSNR binary for star removal and
  denoise (**nothing is bundled** - see [THIRD_PARTY.md](THIRD_PARTY.md)).
- **Wide input support** - 8/16-bit JPEG/PNG/TIFF, FITS, and camera RAW.
- **Edit milestones**, **English + French** UI, light / dark themes.
- **AstroDex integration** - capture in AstroDex, enhance here, send back over a
  signed webhook. Or work fully standalone: upload, edit, download.

A full tour is in [docs/FEATURES.md](docs/FEATURES.md).

**Why this tool?** Something simple and quick that still gives nice results: no
complex pipeline, no cloud dependency, my data under my control.

**Does it replace PixInsight / Siril?** No, and that isn't the goal - think of it
as a fast, self-hosted companion for everyday enhancement.

## Quick start (Docker)

No `.env` editing required - the compose file carries only structural variables,
and everything tunable is set from **Settings** in the UI (stored on the data
volume).

```bash
curl -O https://raw.githubusercontent.com/myastroboard/myastroshine/main/docker-compose.yml
docker compose up -d          # pulls the published image

curl http://localhost:8002/api/health
open  http://localhost:8002
```

One image serves both the API and the web UI. `docker compose up -d` pulls the
published image; if you cloned the repo, `docker compose up -d --build` builds
from the local `Dockerfile` instead. Pin a version with
`MYASTROSHINE_VERSION=0.2.0 docker compose up -d`.

For development with hot reload (uvicorn `--reload` + Vite HMR, source
bind-mounted):

```bash
docker compose -f docker-compose.dev.yml up
```

Full deployment reference: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Local development

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload --port 8002
pytest
```

### Frontend

```bash
cd frontend
npm install
npm run dev                     # Vite dev server on :3000
```

### Checks (what CI runs)

```bash
cd backend  && ruff format --check . && ruff check . && mypy app && pytest
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
python scripts/check_deps_fresh.py     # every dependency pinned to its latest release
python scripts/validate_i18n.py        # if you touched frontend UI text
```

`CONTRIBUTING.md` has the full workflow; `AGENTS.md` the hard rules.

## Documentation

| | |
|---|---|
| [docs/FEATURES.md](docs/FEATURES.md) | What every feature does, step by step |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Services, request flow, storage, module boundaries |
| [docs/API.md](docs/API.md) | HTTP + WebSocket contract, parameters, errors |
| [docs/ALGORITHMS.md](docs/ALGORITHMS.md) | The image-processing and stacking maths |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Configuration, the data volume, ML engines, migrations |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common problems |
| [docs/DESIGN.md](docs/DESIGN.md) | The frontend visual system |
| [CHANGELOG.md](CHANGELOG.md) | What has landed, and what is still open |

The docs index is [docs/README.md](docs/README.md).

## Technology

- **Backend** - FastAPI, Python 3.14, OpenCV, Pillow, NumPy, astropy (FITS),
  rawpy/libraw (camera RAW)
- **Frontend** - React 19, TypeScript, Vite, Tailwind CSS v4
- **Jobs** - Celery + Redis (optional; `PROCESSING_MODE=queue`)
- **Storage** - local filesystem + SQLite (Alembic migrations; Postgres-ready)
- **Packaging** - one multi-arch Docker image (`linux/amd64`, `linux/arm64`)

The API listens on port **8002**. Repository layout:

```
myastroshine/
|-- backend/     FastAPI + OpenCV image-processing engine
|-- frontend/    React + TypeScript + Vite single-page app
|-- docs/        architecture, API, algorithms, deployment, design
|-- engines/     optional operator-installed ML binaries (git-ignored, nothing bundled)
|-- scripts/     maintenance scripts (dependency freshness, i18n parity, changelog)
|-- docker-compose.yml / docker-compose.dev.yml
```

## Contributing

Issues and pull requests welcome - see [CONTRIBUTING.md](CONTRIBUTING.md) and
[AGENTS.md](AGENTS.md) first. Report a bug or request a feature through the
[issue templates](https://github.com/myastroboard/myastroshine/issues/new/choose);
security reports go through the [security policy](SECURITY.md), not a public
issue.

## About

MyAstroShine is developed with the help of
[Claude Code](https://claude.com/claude-code). Architecture and design decisions,
review, and every merge to `main` are done by the human maintainer.

Licensed under [AGPL-3.0-or-later](LICENSE).
