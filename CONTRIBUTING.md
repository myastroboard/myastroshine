# Contributing to MyAstroShine

Thanks for helping build MyAstroShine. This guide covers the practical workflow;
`AGENTS.md` holds the hard rules that also apply to human contributors.

## Development environment

- Python 3.14, Node.js 24+, Docker Desktop 4.0+
- See `README.md` for backend and frontend setup.

## Docker

Both stacks build from the single root `Dockerfile` (multi-stage: a Node
stage builds the frontend, a Python stage runs it); the compose file decides
the command, mounts, environment, and which `target:` to build (`backend` -
API/worker only, skips the frontend build - or the default last stage,
`backend-with-frontend`, which also bakes in the built web UI).

### Debug stack (hot reload)

```bash
docker compose -f docker-compose.dev.yml up          # add --build after editing a Dockerfile or requirements
```

- API under `uvicorn --reload`, worker restarted by `watchmedo`, web on the Vite
  dev server - all with the source bind-mounted from the host.
- `APP_ENV=development`, `LOG_LEVEL=debug`, `PROCESSING_MODE=sync`.
  Prefix with `PROCESSING_MODE=queue` to exercise the Celery + Redis path.
- Data and the SQLite DB land in `./data/` on the host.
- Follow one service: `docker compose -f docker-compose.dev.yml logs -f api`
- Tear down: `docker compose -f docker-compose.dev.yml down` (`-v` also drops the
  `node_modules` volume).

### Release build (production image check)

Run this before tagging a release to confirm the shipped image builds clean and
boots (no `.env` needed - the compose file carries the structural variables):

```bash
docker compose build --no-cache --pull              # baked image, no bind mount
docker compose up -d

curl -f http://localhost:8002/api/health            # -> {"status": "healthy", ...}
docker compose ps                                   # api must reach "healthy"
# open http://localhost:8002                        # same image serves the web UI too

docker compose down -v                              # clean up (drops data volumes)
```

This runs `APP_ENV=production` with `PROCESSING_MODE=queue`, so it also covers the
worker and Redis services that the debug stack skips by default.

### Cutting a release

`VERSION` at the repo root is the single source of truth for the app version
(`backend/app/__init__.py` and `frontend/vite.config.ts` both read it; the
Docker image gets it baked in via a build arg). To tag a release:

1. Run the release build check above.
2. `echo 0.2.0 > VERSION`, commit, merge to `main`.
3. `git tag -a v0.2.0 -m "Release v0.2.0"` then `git push origin v0.2.0`.
4. The tag push triggers `.github/workflows/release.yml`: multi-arch build
   and push of one image to both `ghcr.io/myastroboard/myastroshine` and
   Docker Hub's `myastroboard/myastroshine` (tags `X.Y.Z` / `X.Y` / `X` /
   `latest` on each), a Trivy scan, and a GitHub Release with notes generated
   from `CHANGELOG.md`'s `[Unreleased]` section plus the commit log.
5. `.github/workflows/post-release-cleanup.yml` then opens a PR that files
   that section under `## [0.2.0] - <date>` and resets `[Unreleased]` to
   empty (`scripts/changelog_release.py`) - review and merge it.

**One-time setup, before the first release:**

- **`packages: write` for GitHub Actions** - `release.yml` needs this to push
  images to `ghcr.io`. Repo Settings -> Actions -> General -> Workflow
  permissions -> "Read and write permissions". No secret to create; this
  unlocks what the automatic `GITHUB_TOKEN` is allowed to do for this repo.
- **`DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` secrets** - for the Docker Hub
  push. 1. Create the `myastroboard/myastroshine` repository on
  hub.docker.com if it doesn't exist yet (Docker Hub -> **Create Repository**,
  under the `myastroboard` org). 2. hub.docker.com -> your avatar ->
  **Account Settings** -> **Security** -> **New Access Token**, scope
  **Read & Write**. 3. In `myastroshine`'s repo Settings -> **Secrets and
  variables** -> **Actions**, add `DOCKERHUB_USERNAME` (your Docker Hub
  username) and `DOCKERHUB_TOKEN` (the token from step 2).
- **`GH_PAT` secret** - `post-release-cleanup.yml` pushes a branch and opens a
  PR after a release. Using the automatic `GITHUB_TOKEN` for that would work,
  but GitHub deliberately does not trigger CI on pushes/PRs made with that
  token (to avoid a workflow triggering itself in a loop), so the cleanup PR
  would sit there without a green check. A personal access token isn't
  subject to that restriction, so CI runs on the PR like any other - same
  pattern as myastroboard's `GH_PAT`. To create one:
  1. github.com -> your avatar -> **Settings** -> **Developer settings** ->
     **Personal access tokens** -> **Fine-grained tokens** -> **Generate new
     token**.
  2. Resource owner: `myastroboard`. Repository access: **Only select
     repositories** -> `myastroshine`.
  3. Permissions: **Contents** - Read and write, **Pull requests** - Read and
     write. Nothing else needed.
  4. Set an expiration (GitHub caps fine-grained tokens at 1 year; put a
     calendar reminder to rotate it).
  5. Copy the generated token, then in `myastroshine`'s repo Settings ->
     **Secrets and variables** -> **Actions** -> **New repository secret** ->
     name it `GH_PAT`, paste the value.
  - If you skip this, the cleanup PR still gets created - you'll just need to
    trigger CI on it yourself (push an empty commit, or re-run via the Actions
    tab) before merging.

**Docker Hub description**: `.github/workflows/dockerhub-description.yml`
pushes `DOCKER_HUB.md` as the repo's long description and a short tagline to
`hub.docker.com/r/myastroboard/myastroshine`. It's `workflow_dispatch`-only
(not tied to a release) - reuses the `DOCKERHUB_*` secrets above. Run it once
after the first release, and again whenever `DOCKER_HUB.md` changes
meaningfully (Actions tab -> "Update Docker Hub Description" -> Run workflow).

## Dependencies

All dependencies are pinned to their latest release. `scripts/check_deps_fresh.py`
(and the `Dependency freshness` CI job) fails when a pin falls behind PyPI or npm.
When you bump one, update the pin in `backend/requirements*.txt` or
`frontend/package.json`, or add a documented hold to `scripts/deps_fresh_ignore.txt`.

## Branching and commits

- Branch from `main` as `feature/<short-description>` or `fix/<short-description>`.
- Keep the branch rebased on the latest `main`; resolve conflicts yourself.
- Conventional commit subjects: `feat:`, `fix:`, `docs:`, `style:`, `refactor:`,
  `test:`, `chore:` in imperative mood, <= 72 chars.
- The maintainer performs every merge and every commit to `main`.

## Backend checks

Run from `backend/`:

```bash
ruff format .          # formatter (config shared from ../ruff.toml)
ruff check .           # linter
mypy app               # type checker
pytest                 # test suite (target: 85%+ coverage)
```

`pytest` includes `test_deps_fresh.py`, which queries PyPI/npm; it skips itself
when offline or when `SKIP_DEPS_FRESH=1` is set.

`tests/benchmarks/` (full-res enhance < 5s, slider response < 500ms, stacking
SNR gain ~sqrt(N)) is the opposite: skipped by default, since wall-clock
budgets are sensitive to the machine running them. Run explicitly, without
coverage (which measurably slows CPython down):

```bash
RUN_BENCHMARKS=1 pytest tests/benchmarks --no-cov -v
```

Runs weekly in CI (`.github/workflows/benchmarks.yml`) as a signal to
investigate, not a merge gate.

- Tests mirror the source tree: `app/services/foo.py` -> `tests/services/test_foo.py`.
- Validate all external input through `app/utils/validators.py`.

### Logging

- Always `logger = get_logger(__name__)` from `app.logging_config`; never
  `print()`, never `import logging` or configure a handler yourself.
- Pick the level deliberately (`debug` / `info` / `warning` / `error`) and pass
  context as keywords: `logger.info("stack combined", stack_id=sid, frames=n)`.
- Two sinks: the console (`docker logs`, level `console_log_level`) and a
  rotating file `DATA_DIR/myastroshine.log` (10 MB x 5, level `log_level`). Both
  levels are runtime settings; the Celery worker writes `worker.log`.
- Users read and export logs from **Settings -> Logs**; the export ZIP is what
  to attach to a bug report.

## Frontend checks

Run from `frontend/`:

```bash
npm run lint           # eslint
npm run typecheck      # tsc --noEmit
npm test               # vitest (unit + component)
npm run build          # production build must succeed
npm run test:e2e       # Playwright (boots the backend + Vite, drives Chromium)
```

`test:e2e` needs the browser (`npx playwright install chromium`, once) and the
backend importable (`pip install -r ../backend/requirements.txt`). It runs as its
own `e2e` CI job.

- No `innerHTML`, no static inline styles (see `AGENTS.md` section 5).
- Components are function components with typed props; hooks live in `src/hooks/`.
- All frontend types are camelCase. The backend speaks snake_case; conversion
  happens only in `src/services/api.ts` / `ws.ts` via `caseConvert.ts`. Do not
  add snake_case to component/hook/type code.
- Tailwind v4 is configured CSS-first in `src/styles/index.css` (`@theme`), loaded
  by the `@tailwindcss/vite` plugin - there is no `tailwind.config.js`.
- Follow `docs/DESIGN.md` - the design charter shared with MyAstroBoard (teal +
  amber accents, navy-teal glass surfaces). Compose the shared component classes
  (`.panel`, `.btn`, `.field`, `.slider`, ...) and semantic tokens; never a raw
  hex colour or a new font in a component.

## Pull requests

- Describe what changed and why. Link the issue (`Fixes #123`).
- Include tests for new behavior.
- Update `docs/` and `CHANGELOG` for any user-facing or behavioral change.
- CI must be green before review.

## Project layout

| Path | Purpose |
|------|---------|
| `backend/app/routes/` | FastAPI routers (HTTP + WebSocket) |
| `backend/app/services/` | business logic, one responsibility per file |
| `backend/app/models/` | Pydantic request/response models |
| `backend/app/db/` | SQLAlchemy ORM models and session management |
| `backend/app/utils/` | shared helpers (image IO, math, validation) |
| `frontend/src/components/` | React components |
| `frontend/src/hooks/` | custom hooks |
| `frontend/src/services/` | API and WebSocket clients |
