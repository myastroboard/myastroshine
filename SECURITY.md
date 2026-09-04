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

MyAstroShine is a **self-hosted, single-operator application**. It has no
built-in user-account system - it's designed for one person or household
running one deployment, on:

- A personal home server or NAS
- A private network / VPN
- Optionally behind a reverse proxy with its own authentication

There is no login screen and no per-user permission model. The `ADMIN_ENABLED`
setting (on by default, see `docs/DEPLOYMENT.md`) is a coarse kill-switch for
the administrative surface (`/api/admin/*`, `/api/tokens`) - not
authentication. Anyone who can reach the API is trusted to the same degree the
UI is trusted. Treat network exposure as the actual access-control boundary:
don't expose this API directly to the public internet without a reverse proxy
that adds real authentication in front of it.

### What's protected today

- **Input validation**: every request body is a Pydantic model; session/stack
  identifiers are validated as well-formed UUIDs and checked against the
  database before touching the filesystem - user input never builds a file
  path directly (`app/utils/validators.py`, `app/services/storage.py`).
- **Upload safety**: uploads are size-capped before decoding
  (`max_image_size_mb`), and the decoded pixel count is capped too
  (`app/utils/image_utils.py:decode_image`) - a small file that would
  decompress into a huge array is rejected rather than trusted.
- **AstroDex webhook callback URLs fail closed**: an empty
  `astrodex_callback_urls` allowlist rejects every callback URL rather than
  allowing all of them. Configure at least one entry before enabling AstroDex
  webhook delivery, or requests to `/api/send-to-astrodex` and
  `/api/astrodex/receive` are refused. This is the main defense against the
  server being used to make requests to arbitrary internal/external hosts
  (SSRF) via the webhook feature.
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
  routes, plus a separate per-IP concurrent-job cap (`docs/API.md` "Rate
  Limiting").
- **Error handling**: the shared error envelope never includes a stack trace,
  file path, or other internal detail in a response body.

### Intentional scope boundaries

- **No multi-user auth.** This is a deliberate design choice for a
  single-operator tool, not an oversight - see "Security Model" above.
- **`ADMIN_ENABLED` is a feature toggle, not a credential.** When it's `true`
  (the default), `/api/admin/*` and `/api/tokens` behave like the rest of the
  API: reachable by anyone who can reach the API at all. Set it `false` to
  disable that surface entirely on a deployment where you don't need it.
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
