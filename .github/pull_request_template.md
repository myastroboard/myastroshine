<!-- Keep it short. The "why" matters more than a blow-by-blow of the diff. -->

## What & why

<!-- What changes, and what problem it solves. -->

## Related issues

<!-- e.g. Fixes #123 - or "none" -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor / internal only
- [ ] Docs
- [ ] Breaking change (API, storage layout, or settings)

## Screenshots

<!-- Before / after for any UI change. Delete this section otherwise. -->

## Checklist

- [ ] Branch is `feature/...` or `fix/...`, rebased on the latest `main`
- [ ] Backend green: `ruff format . && ruff check . && mypy app && pytest`
- [ ] Frontend green: `npm run lint && npm run typecheck && npm test && npm run build`
- [ ] Tests added or updated for the change
- [ ] `CHANGELOG.md` (`[Unreleased]`) and `docs/` updated for any user-facing change
- [ ] All code and comments in English; no `print()` in the backend (use `get_logger`)
