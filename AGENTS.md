# Working rules for AI assistants

Project-specific rules for any AI coding assistant working in this repository.
Keep the "Non-negotiables" section intact.

---

## 1. Non-negotiables

- **Never run `git commit`.** The human does every commit on this repo. Proposing a
  commit message they can copy is fine; performing the commit is not.
- **Never offer or ask to commit.** Staging or showing a diff on request is fine.
- **Never push, force-push, rebase-onto-shared, or rewrite published history**
  without an explicit request.
- **Always add attribution lines** ("Generated with...", "Co-Authored-By: ...") to
  commit messages or pull request descriptions, but never add link to the session.
- **Never skip or disable hooks / signing / CI** unless explicitly asked. If a hook
  fails, fix the cause.
- **Report outcomes honestly.** If tests fail, say so and show the output.

## 2. Before you write any code

- Read `CONTRIBUTING.md`, this file, and the relevant `docs/*.md` for the subsystem
  you are about to touch (`docs/API.md`, `docs/ALGORITHMS.md`, `docs/DEPLOYMENT.md`).
- Match the surrounding code: naming, idioms, comment density, file layout,
  error-handling style.
- Prefer editing existing files over adding new ones. Do not introduce a new
  framework, dependency, or architectural pattern to solve a local problem.

## 3. Language and text

- All code, comments, docstrings, commit messages, PR text, and user-facing strings
  in **English**.
- **ASCII punctuation only** in source text. Straight apostrophe `'` (U+0027), never
  the curly `U+2019`. Hyphen-minus `-` (U+002D), never en/em dashes.

## 4. Logging and output

- Backend: use `from app.logging_config import get_logger` then
  `logger = get_logger(__name__)`.
- **Never** use `print()` / `console.log` for diagnostics in committed code.
- **Never** import the raw `logging` library directly or configure your own handlers.
- Pick the right level and include context (inputs, paths, ids) in the message.

## 5. Frontend

- **No `innerHTML`** or equivalent HTML-string sinks. Build UI with React / explicit
  DOM APIs; use `textContent` for any user- or API-derived text.
- **No static inline styles.** Put static presentation in a CSS class or a Tailwind
  utility. Allowed: runtime show/hide and genuinely per-instance dynamic values
  (a computed pixel offset for the depth-shift parallax, a progress-bar width).
- Keep the existing stack (React 19 + Vite + Tailwind v4). No new frameworks.
- Mobile-first / responsive: verify layout at small widths.

## 6. Architecture and module boundaries

- One class / responsibility per file where practical; separate data loading,
  business logic, and presentation.
- `routes/` may import `services/`; `services/` must not import `routes/`.
- A helper needed by two features belongs in `app/utils/`. Do not add a module-level
  import that closes a dependency cycle.

## 7. Data correctness

- **Validate all external/user input** before saving it, using it in a file path
  (use `app/utils/validators.py`, do not roll your own), or returning it in a
  response.
- No hardcoded data that silently goes stale.

## 8. Refactoring safety

- After any rename of a cross-file contract (function signature, kwarg, dict key,
  config key, API route), grep the entire repo for the old identifier before calling
  it done.
- After a large mechanical change, run the full test suite, not just the touched file.

## 9. Tests

- Place tests mirroring the source layout
  (`app/services/foo.py` -> `tests/services/test_foo.py`).
- Descriptive test names with a docstring stating the behavior under test.
- Never cite source line numbers or coverage branch-arcs in test docstrings.
- Test the success path, the failure path, and edge/boundary cases. Mock external
  dependencies (network, containers, clock, third-party APIs).
- New behavior ships with tests that prove it works.

## 10. Git workflow

- Work on a branch named `feature/<short-description>` or `fix/<short-description>`.
  If you find yourself on the default branch, branch first.
- Commit message format (for messages you propose):

  ```
  <type>: <subject in imperative mood, <= 72 chars>

  <body: what and why, wrapped>

  <footer: "Fixes #123" etc.>
  ```

  Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`.

## 11. Definition of done

Do not report a change as complete until the project check set passes:

- [ ] `pytest` (backend) / `npm test` (frontend)
- [ ] `ruff format --check .` and `ruff check .` (from repo root; config in `ruff.toml`)
- [ ] `mypy app` (backend)
- [ ] `npm run lint` and `npm run typecheck` (frontend)
- [ ] `python scripts/check_deps_fresh.py` passes (no dependency left behind)
- [ ] Contract tests updated if you added/removed/renamed a route or public API
- [ ] Docs updated for any user-facing or behavioral change
- [ ] All new text in English / ASCII punctuation
- [ ] No `print()` / raw logging import; no `innerHTML`; no new static inline styles

Report which commands you actually ran and their results.
