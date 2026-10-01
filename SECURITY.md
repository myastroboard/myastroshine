# Security Policy

## Supported Versions

We provide security fixes for the following versions of MyAstroShine:

| Version | Supported          |
| ------- | ------------------ |
| latest  | :white_check_mark: |
| < latest| :x:                |

We recommend always running the latest release to get the most recent security
fixes.

## Security Model

MyAstroShine is a **self-hosted, single-operator application**, designed for
one person or household running one deployment, on:

- A personal home server or NAS
- A private network / VPN
- Optionally behind a reverse proxy with its own authentication

It works like professional software: anyone who reaches it can **use** it
(upload, edit, stack, download, presets), but the **administration** - Settings,
logs, job history, webhook tokens, configuration import/export - is behind an
**admin password** (`docs/API.md` "Admin authentication"). There is one admin
password and no user accounts or per-user permissions.

Using the app stays open by design, so network exposure is still the
access-control boundary for that part: don't expose MyAstroShine directly to the
public internet without a reverse proxy that adds authentication in front of it.

**First run.** Until an admin password is set, the administration surface is
locked (never open), and the first visitor to open Settings chooses the
password. Set it right after installing, before the instance is reachable by
others. A lost password is reset from the host with
`docker exec myastroshine-api python -m app.cli reset-admin`.

### What's protected today

- **Admin authentication**: the admin password is stored as a salted scrypt
  hash (N=2^15, r=8, p=3 - an OWASP Password Storage Cheat Sheet equivalent of
  N=2^17, p=1; a hash made with a weaker cost is upgraded at the next login); a login is a random token in an `HttpOnly`, `SameSite=Strict` cookie
  (only its SHA-256 hash is stored), ending after `admin_session_idle_days`
  without use and 30 days at most, and at once on a password change for every
  other browser. Failed logins are throttled per IP with doubling lockouts.
  State-changing admin requests from another origin are refused, which
  `SameSite` alone would not catch for another app on the same host.

- **Input validation**: every request body is a Pydantic model; session/stack
  identifiers are validated as well-formed UUIDs and checked against the
  database before touching the filesystem - user input never builds a file
  path directly (`app/utils/validators.py`, `app/services/storage.py`).
- **Upload safety**: every file is size-capped (`max_image_size_mb`) from
  its spooled size before it is read, a request declaring more than its route
  can carry is refused before its body is received, batches are capped at 20
  files, and an archive member is checked on its declared size before it is
  unpacked. Uploads are processed a file at a time, never held in memory whole.
  The decoded pixel count is capped too (`app/utils/image_utils.py:decode_image`)
  - a small file that would decompress into a huge array is rejected rather
  than trusted.
- **AstroDex callback URLs fail closed**: an empty `astrodex_callback_urls`
  allowlist rejects every callback. A handoff token carries the board origin it
  was minted with (`callback_base`); `/api/astrodex/handoff/resume` refuses it
  unless that origin is on the allowlist, before making any outbound request.
  Configure at least one entry before using the integration. This is the main
  defense against the server being pointed at arbitrary internal/external hosts
  (SSRF) through the handoff.
- **Handoff tokens** are HMAC-SHA256 signed with a webhook token's
  `signing_secret`, expire after 12 h, and are single-use for the return leg
  (the board rejects a replayed `jti`). A tampered or expired token is a `401`.
- **CORS**: `cors_origins` rejects a literal `"*"` entry - the API always sets
  `allow_credentials=True`, so a wildcard origin would be a real hole, not
  just a combination browsers already reject.
- **Secrets**: the session secret and each webhook token's signing secret are
  generated with `secrets.token_hex(32)`, written once to the data volume
  (`0600` where the OS supports it), and never appear in an environment
  variable or a git-tracked file.
- **SQL injection**: all database access goes through SQLAlchemy's ORM / typed
  `select()` - no raw SQL string formatting anywhere in the codebase.
- **XSS**: the frontend never uses `dangerouslySetInnerHTML` or `innerHTML`;
  React's default JSX escaping is the only rendering path.
- **Rate limiting**: per-IP request limits cover the full API surface,
  including `/api/tokens`, `/api/admin/*`, `/api/download/*`, and the AstroDex
  handoff routes, plus a separate per-IP concurrent-job cap (`docs/API.md`
  "Rate Limiting").
- **Error handling**: the shared error envelope never includes a stack trace,
  file path, or other internal detail in a response body.

- **Engine uploads**: installing a StarNet2 / DeepSNR package runs a binary on
  the server, so it is admin-only. The archive is unpacked defensively (no path
  or link leaving it, no special files, size and entry caps), must contain a
  Linux binary for the server's architecture, and is only installed after the
  admin accepted its licence. Installed engine files are never served back.

### Intentional scope boundaries

- **No multi-user auth.** One admin password, no accounts or roles - a
  deliberate choice for a single-operator tool. Using the app (as opposed to
  administering it) needs no login at all.
- **`ADMIN_ENABLED`** is a structural kill-switch, on top of the admin
  password: set it `false` to turn the administration surface off entirely.
- **Denial of service** from a determined attacker with network access isn't
  in scope - the in-memory, single-process rate limiter is meant to keep a
  normal editing session (and accidental client bugs) from overwhelming the
  server, not to withstand a deliberate flood. Put this behind a reverse proxy
  or firewall if you're exposed to untrusted networks.
- **Vulnerabilities in third-party services** MyAstroShine talks to (AstroDex,
  the container registry) are out of scope for this policy.

## Reporting a Vulnerability

Please don't report security vulnerabilities through public GitHub issues.

1. **Open a private security advisory** on GitHub: go to the repository's
   Security tab -> "Report a vulnerability", and fill out the form.
2. If that's not possible, open a private issue and tag the maintainers.

Please include: the type of vulnerability, affected file(s)/route(s), steps to
reproduce, and (if you have one) a suggested fix. We'll acknowledge new reports
within a few days and aim to ship a fix before any public disclosure.

## Keeping a Deployment Current

```bash
docker compose pull
docker compose up -d
```

- Dependencies are pinned and checked weekly for both staleness
  (`scripts/check_deps_fresh.py`, `.github/workflows/deps-fresh.yml`) and known
  CVEs (`pip-audit` / `npm audit` in CI, plus a Trivy scan on every published
  image).
- Review `docker-compose.yml`'s CORS/AstroDex settings in Settings -> Advanced
  if this deployment is reachable from more than your own machine.

## References

- [OWASP Top Ten](https://owasp.org/www-project-top-ten/)
- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
