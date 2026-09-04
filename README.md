# MyAstroShine

**Status:** Alpha - v0.1.0, unreleased
**License:** AGPL-3.0-or-later
**Ecosystem:** MyAstroBoard / AstroDex integration + Standalone

> **Alpha software.** MyAstroShine is under active development and has never been
> tagged or released. The full v1.0 + v1.1 feature set is implemented and the
> frontend is wired end to end, but the code has not been through a production
> shakedown. Expect breaking changes to the API, storage layout, and settings
> between commits; there are no published Docker images or version tags yet, and
> nothing here should be relied on for irreplaceable data. See the
> [Known gaps](CHANGELOG.md#known-gaps) in the changelog.

MyAstroShine is an astronomical image processing tool: automatic enhancement,
multi-image stacking, and visual effects. It integrates optionally with AstroDex
but also runs standalone.

- **Algorithmic enhancement**: contrast, clarity, noise reduction, dynamic stretching
- **Adjustment sliders**: real-time fine-tuning of every parameter
- **Geometry**: rotate, flip, straighten, and crop before the pixel pipeline runs
- **Depth Shift**: a parallax effect that adds a sense of 3D depth
- **Stacking (v1.1+)**: align and combine 5-100 frames to raise SNR
- **Presets**: five built-ins plus user presets, applied to any session
- **AstroDex integration**: capture in AstroDex, enhance here, send back via signed webhook
- **Standalone workflow**: manual upload, edit, download

## Repository layout

```
myastroshine/
|-- backend/     FastAPI + OpenCV image processing engine
|-- frontend/    React + TypeScript + Vite single-page app
|-- docs/        API, algorithm, and deployment documentation
|-- scripts/     maintenance scripts (dependency freshness check)
|-- docker-compose.yml
```

The full design lives in `docs/`. [CHANGELOG.md](CHANGELOG.md) tracks what has
landed.

## Quick start (Docker)

No `.env` editing required - the compose file carries only the structural
variables, and everything tunable is set from **Settings** in the UI (stored
under the data volume). See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

```bash
docker compose build
docker compose up -d

curl http://localhost:8002/api/health
open http://localhost:3000
```

For development with hot reload (uvicorn `--reload` + Vite HMR, source
bind-mounted):

```bash
docker compose -f docker-compose.dev.yml up
```

## Local development

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload --port 8002
pytest
```

### Frontend

```bash
cd frontend
npm install
npm run dev                    # Vite dev server on :3000
```

### Dependency freshness

Every dependency is pinned to its latest release. Verify at any time:

```bash
python scripts/check_deps_fresh.py
```

CI runs this weekly; it is also part of `pytest` (skipped when offline).

## Technology stack

- **Backend**: FastAPI, Python 3.13, OpenCV, scikit-image, Pillow
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS v4
- **Jobs**: Celery + Redis (optional; `PROCESSING_MODE=queue`)
- **Storage**: local filesystem + SQLite for metadata
- **Containerization**: Docker + Docker Compose

The API listens on port **8002** (8000 is left for other local projects).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md) before opening a
pull request.

## Roadmap to 1.0.0

The feature work is done; the remaining items before a first tag are tracked in
[CHANGELOG.md](CHANGELOG.md#known-gaps): a load/performance suite and
published Docker images.

## About

MyAstroShine is developed with the help of
[Claude Code](https://claude.com/claude-code).
Architecture and design decisions, review, and every merge to `main` are done by
the human maintainer.
