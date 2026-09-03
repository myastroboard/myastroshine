# Contributing to MyAstroShine

Thanks for helping build MyAstroShine. This guide covers the practical workflow;
`AGENTS.md` holds the hard rules that also apply to human contributors.

## Development environment

- Python 3.13, Node.js 24+, Docker Desktop 4.0+
- See `README.md` for backend and frontend setup.

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

- Tests mirror the source tree: `app/services/foo.py` -> `tests/services/test_foo.py`.
- Use `get_logger(__name__)` from `app.logging_config`; never `print()`.
- Validate all external input through `app/utils/validators.py`.

## Frontend checks

Run from `frontend/`:

```bash
npm run lint           # eslint
npm run typecheck      # tsc --noEmit
npm test               # vitest
npm run build          # production build must succeed
```

- No `innerHTML`, no static inline styles (see `AGENTS.md` section 5).
- Components are function components with typed props; hooks live in `src/hooks/`.
- Tailwind v4 is configured CSS-first in `src/styles/index.css` (`@theme`), loaded
  by the `@tailwindcss/vite` plugin - there is no `tailwind.config.js`.

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
