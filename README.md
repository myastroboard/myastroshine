# MyAstroShine

**Status:** Implementation - all v1.0 + v1.1 API routes implemented (enhance,
presets, depth shift, AstroDex webhooks, stacking, Celery queue + progress WS);
frontend wired end to end for both single-image and multi-frame stacking
**License:** AGPL-3.0-or-later
**Ecosystem:** MyAstroBoard / AstroDex integration + Standalone

MyAstroShine is a complete astronomical image processing tool: automatic
enhancement, multi-image stacking, and visual effects. It integrates optionally
with AstroDex but also runs standalone.

- **Algorithmic enhancement**: contrast, clarity, noise reduction, dynamic stretching
- **Adjustment sliders**: real-time fine-tuning of every parameter
- **Depth Shift**: a parallax effect that adds a sense of 3D depth
- **Stacking (v1.1+)**: align and combine 5-100 frames to raise SNR
- **AstroDex integration**: capture in AstroDex, enhance here, send back
- **Standalone workflow**: manual upload, edit, download

## Repository layout

```
myastroshine/
|-- backend/     FastAPI + OpenCV image processing engine
|-- frontend/    React + TypeScript + Vite single-page app
|-- docs/        API, algorithm, and deployment documentation
|-- docker-compose.yml
```

The full design lives in `docs/` and in the planning documents.

## Quick start (Docker)

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
# edit the .env files as needed

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
- **Jobs**: Celery + Redis (optional, phase 2+)
- **Storage**: local filesystem + SQLite for metadata
- **Containerization**: Docker + Docker Compose

The API listens on port **8002** (8000 is left for other local projects).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md) before opening a
pull request.
