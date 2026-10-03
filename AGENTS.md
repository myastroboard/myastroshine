# Working rules for AI assistants

Project-specific rules for any AI coding assistant working in this repository. They sit on top
of the **organization standards** shared by every MyAstroBoard repository, synced into this
repository and imported here:

@.github/instructions/org-standards.instructions.md

Those apply in full. Do not edit the synced copy: change it in
[myastroboard/.github](https://github.com/myastroboard/.github/tree/main/standards). The
sections below keep their numbers (other files refer to them) and only add what is specific to
MyAstroShine.

---

## 1. Non-negotiables

Organization standards, section 1 (no AI commits, AI assistance disclosed with a
`Co-Authored-By:` trailer, never skip hooks or CI, honest reporting, pseudonymous maintainer,
no secrets).

## 2. Before you write any code

- Read `CONTRIBUTING.md`, this file, and the relevant `docs/*.md` for the subsystem
  you are about to touch: [`docs/README.md`](docs/README.md) indexes them -
  `ARCHITECTURE.md` (topology), `API.md` (contract), `ALGORITHMS.md` (the maths),
  `DEPLOYMENT.md` (config), `DESIGN.md` (the frontend visual system).

## 3. Language and text

- Frontend UI text is translated: FR + EN, `frontend/src/i18n/translations/*.json`
  (`en.json` is the reference language). Add a UI string as a key there and read it
  with `useTranslation()`'s `t()` (`@/hooks/useTranslation`), never hardcode text in
  a component. `python scripts/validate_i18n.py` checks key, type and placeholder
  parity, and runs in CI.

## 4. Logging and output

- Backend: `from app.logging_config import get_logger` then `logger = get_logger(__name__)`,
  with context passed as keywords: `logger.info("stack combined", stack_id=sid, frames=n)`.

## 5. Frontend

- **No HTML-string sinks** (organization standards, section 5); `frontend/eslint.config.js`
  enforces it.
- **No static inline styles.** Static presentation goes in a CSS class or a Tailwind utility.
  Allowed: runtime show/hide and genuinely per-instance dynamic values (a computed pixel offset
  for the depth-shift parallax, a progress-bar width).
- **Both themes, always.** The app ships light (default) and dark, switched from
  the footer. Style through the semantic tokens in `src/styles/index.css`
  (`bg-surface`, `text-muted`, `hover:bg-hover`, ...) - never a hardcoded
  light/dark-specific colour (`bg-white/10`, `text-white`, a raw hex). A missing
  token gets added with a `.dark` override. Exception: chrome layered on top of
  an image stays dark in both themes (see `docs/DESIGN.md`). Verify new surfaces
  in both themes.
- **Surfaces: `.panel` or `.panel-inset`, nothing else.** `.panel` frames a
  region; `.panel-inset` is a block nested inside one. Don't hand-roll
  `rounded border bg-surface`.
- Keep the existing stack (React 19 + Vite + Tailwind v4). No new frameworks.

## 6. Architecture and module boundaries

- `routes/` may import `services/`; `services/` must not import `routes/`.
- A helper needed by two features belongs in `app/utils/`. Do not add a module-level
  import that closes a dependency cycle.

## 7. Data correctness

- Validate external and user input with `app/utils/validators.py`; do not roll your own.

## 8. Refactoring safety

Organization standards, section 9.

## 9. Tests

- Backend tests mirror the source layout (`app/services/foo.py` ->
  `tests/services/test_foo.py`); coverage target 85%+ backend, 95% per file frontend.
- `tests/regression/` holds golden-image tests: a deliberate pipeline change updates the
  references (`UPDATE_GOLDEN=1 pytest tests/regression`), it does not loosen the comparison.

## 10. Git workflow

Organization standards, section 11 (branches, conventional commits) and section 12 (changelog:
a `feature/` or `fix/` branch adds a bullet under `## [Unreleased]`).

## 11. Definition of done

Do not report a change as complete until the project check set passes:

- [ ] `pytest` (backend) / `npm test` (frontend)
- [ ] `ruff format --check .` and `ruff check .` (from repo root; `ruff.toml` extends
      `.github/org/ruff.base.toml`)
- [ ] `mypy app` (backend)
- [ ] `npm run lint` and `npm run typecheck` (frontend)
- [ ] `python scripts/check_deps_fresh.py` passes (no dependency left behind)
- [ ] `python scripts/validate_i18n.py` passes if you touched frontend UI text
- [ ] Contract tests updated if you added/removed/renamed a route or public API
- [ ] The rest of the organization standards' definition of done (section 14)

Report which commands you actually ran and their results.
