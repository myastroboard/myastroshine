# Contributing to MyAstroShine

Thanks for helping build MyAstroShine. This guide covers the practical workflow;
`AGENTS.md` holds the hard rules that also apply to human contributors, on top of the
[organization standards](https://github.com/myastroboard/.github/blob/main/standards/ORG_STANDARDS.md)
shared by every MyAstroBoard repository.

## Development environment

- Python 3.14, Node.js 24+, Docker Desktop 4.0+
- See `README.md` for backend and frontend setup.

## Docker

Both stacks build from the single root `Dockerfile` (multi-stage: a Node
stage builds the frontend, a Python stage runs it); the compose file decides
the command, mounts, environment, and which `target:` to build (`backend` -
API only, skips the frontend build - or the default last stage,
`backend-with-frontend`, which also bakes in the built web UI).

### Debug stack (hot reload)

```bash
docker compose -f docker-compose.dev.yml up          # add --build after editing a Dockerfile or requirements
```

- API under `uvicorn --reload` (it also runs the processing jobs), web on the
  Vite dev server - both with the source bind-mounted from the host.
- `APP_ENV=development`, `LOG_LEVEL=debug`.
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

This runs `APP_ENV=production` from the baked image, exactly as users get it.

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
   that section under `## 0.2.0 (<date>)` and resets `[Unreleased]` to the
   empty template (`scripts/changelog_release.py`) - review and merge it.

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

### CPU compatibility

The amd64 image must keep running on x86-64 CPUs without x86-64-v2 (no
SSE4.2/POPCNT). In practice that is a VM with a generic CPU model, e.g. Proxmox
`kvm64` - the default of the Home Assistant OS VM scripts, so a common setup, not
a legacy one. Some PyPI wheels (current NumPy, for one) require x86-64-v2 and
crash at import there with "Illegal instruction". The `Dockerfile` therefore
rebuilds NumPy from source on amd64 (`REBUILD_FOR_OLD_CPUS`, in the
`python-wheels` stage) with no CPU baseline; it still picks its SSE4 / AVX
kernels at run time on CPUs that have them.

The `CPU compatibility` workflow checks this on every PR that touches
`backend/requirements.txt` or the `Dockerfile`, and the release workflow runs the
same check on the image it is about to publish - a failure there blocks the
release. Run it locally with:

```bash
docker build -t myastroshine:cpu-compat .
sh scripts/check_cpu_compat.sh myastroshine:cpu-compat   # CPU_MODEL=kvm64 by default
```

It runs `scripts/cpu_compat_smoke.py` (imports the app, runs the enhancement
pipeline, star detection, FITS / 16-bit / linear ingest) under QEMU's emulation of
that CPU. When it fails, the log names the root-cause package(s). Then, in order
of preference:

1. **Stay on the current version** - keep the old pin and add a documented hold
   to `scripts/deps_fresh_ignore.txt`. Right for most bumps.
2. **Rebuild the package from source** - add it to `REBUILD_FOR_OLD_CPUS` in the
   `Dockerfile` (e.g. `"numpy rawpy"`), when the update is needed (security fix,
   Python support). The compiler defaults target any x86-64 CPU; a package that
   raises its own baseline (as NumPy does) also needs its build option in the
   rebuild loop, and one with extra build dependencies needs them in the
   `python-wheels` stage. Rebuilding OpenCV would take very long - prefer 1.
3. **Drop support for these CPUs** - a maintainer decision, to be documented and
   announced.

## Branching and commits

Branch names, commit format and AI disclosure follow the
[organization's contributing guide](https://github.com/myastroboard/.github/blob/main/CONTRIBUTING.md).
In short:

- Branch from `main` as `<type>/<short-description>` (`feature/`, `fix/`, `chore/`,
  `docs/`, `refactor/`, `test/`, `ci/`), and keep it rebased on the latest `main`.
- Conventional commit subjects in imperative mood, <= 72 chars.
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

`tests/regression/` is the opposite again: a handful of **golden-image**
tests that run a small synthetic frame through the real enhancement/stacking
pipeline and diff the output against a checked-in reference (`tests/regression/golden/`)
- catches a change that runs cleanly, with no exception, but silently alters
what the pipeline actually produces (numeric drift in a gain/clamp, say).
Included in the default `pytest` run - fast and deterministic, no opt-in. A
deliberate pipeline change updates the references instead of fighting the
test:

```bash
UPDATE_GOLDEN=1 pytest tests/regression -v
```

- Tests mirror the source tree: `app/services/foo.py` -> `tests/services/test_foo.py`.
- Validate all external input through `app/utils/validators.py`.

### Logging

- Always `logger = get_logger(__name__)` from `app.logging_config`; never
  `print()`, never `import logging` or configure a handler yourself.
- Pick the level deliberately (`debug` / `info` / `warning` / `error`) and pass
  context as keywords: `logger.info("stack combined", stack_id=sid, frames=n)`.
- Two sinks: the console (`docker logs`, level `console_log_level`) and a
  rotating file `DATA_DIR/myastroshine.log` (10 MB x 5, level `log_level`). Both
  levels are runtime settings.
- Users read and export logs from **Settings -> Logs**; the export ZIP is what
  to attach to a bug report.

## Frontend checks

Run from `frontend/`:

```bash
npm run lint           # eslint
npm run typecheck      # tsc --noEmit
npm test               # vitest (unit + component) + coverage, 95% per file enforced
npm run build          # production build must succeed
npm run check:dist     # after build: the bundle only uses relative URLs
npm run test:e2e       # Playwright (boots the backend + Vite, drives Chromium)
```

The e2e run starts its own servers on ports 8012 / 3012 / 3112 (never the dev
stack's 8002 / 3000, and it never reuses a running server). Its `ingress`
project builds the app and walks it behind a fake Home Assistant ingress proxy
(`e2e/ingress/`), failing on any request that escapes the path prefix.

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

- Use the [PR template](.github/pull_request_template.md). Describe what changed
  and why; link the issue (`Fixes #123`).
- Include tests for new behavior.
- Update the relevant `docs/*.md` ([docs/README.md](docs/README.md) indexes them)
  for any user-facing or behavioral change.
- A `feature/` or `fix/` branch adds a one- or two-line bullet to `CHANGELOG.md`
  under `## [Unreleased]` (`### Features`, `### Fixes` or `### Breaking changes`,
  replacing the `- None.` placeholder); the `Require Changelog Entry` check fails
  the PR otherwise. Detail goes in `docs/`, linked from the bullet.
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
