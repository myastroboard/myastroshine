# Home Assistant app: lessons from MyAstroBoard, applied to MyAstroShine

Written 2026-09-30, after MyAstroBoard shipped as a Home Assistant app (1.6.4 -> 1.6.8,
repo `myastroboard/home-assistant-apps`, local `D:\Code\home-assistant-apps`).
Goal: list everything we had to discover, fix or build for MyAstroBoard, so the
MyAstroShine app gets it right the first time. Each item says what happened on the
board side, then what it means for MyAstroShine (checked against this repo at 0.4.2).

Sections:

1. [TL;DR - MyAstroShine checklist](#1-tldr---myastroshine-checklist)
2. [How the apps repository works](#2-how-the-apps-repository-works)
3. [Container / image fixes (code side)](#3-container--image-fixes-code-side)
4. [AppArmor](#4-apparmor)
5. [Ingress](#5-ingress)
6. [Test on a real HA instance](#6-test-on-a-real-ha-instance)
7. [Traps we fell into](#7-traps-we-fell-into)
8. [Proposed order of work](#8-proposed-order-of-work)

---

## 1. TL;DR - MyAstroShine checklist

Good news first: MyAstroShine is **much easier** than MyAstroBoard was.

| Topic | MyAstroBoard had to... | MyAstroShine today |
|---|---|---|
| `DATA_DIR=/data` | fix `entrypoint.sh` (hardcoded `/app/data` chown) | already `ENV DATA_DIR=/data` in the image |
| Non-root user switch | replace `su` by `setpriv` (stop exit code) | runs as root, uvicorn is PID 1 (exec form) - nothing to fix |
| HEALTHCHECK in the image | add one (HA has no `watchdog` we could keep) | already there (`/api/health`) |
| multi-arch amd64 + arm64 | already there | already there (release.yml matrix) |
| Server-side templates | ~120 root-absolute URLs in Jinja | none: Vite SPA |
| Client routing | real paths (`/login`, ...) | **hash routing** (`#/settings`): the page path is always the app root |
| Session cookie | rename + path-scope under ingress | no login, no session cookie |
| PWA / service worker / push | disable under ingress, document it | none |

Still to do for MyAstroShine, in order:

1. **Single-container mode**: `PROCESSING_MODE=sync`, no worker, no Redis, **so no Celery
   beat, so `task_cleanup_sessions` never runs** -> sessions, stacks and stale jobs pile
   up in `/data` forever. Fix upstream first (section 3.1).
2. **Old CPUs (amd64)**: `numpy==2.5.3` from PyPI crashes at import on Proxmox `kvm64`
   (the default of the HAOS VM scripts). Same fix as the board (section 3.2).
3. **IPv6 listen**: `uvicorn --host 0.0.0.0` is IPv4-only; `homeassistant.local` often
   resolves to IPv6 -> "Open web UI" fails. Section 3.3 - and read the trap in 3.3 first.
4. **Clean stop within `timeout:`**, including a sync processing request in flight (3.4).
5. **External engines**: `./engines:/opt/engines:ro` bind mount does not exist in HA (3.5).
6. **AppArmor profile**: copy the board one, drop the root-switch capabilities (section 4).
7. **Ingress**: frontend relative URLs (Vite `base`, `api.ts`, `ws.ts`, `/logo.png`) +
   backend client-IP restore (rate limiter and per-IP job limit!) (section 5).
8. **Security decision**: MyAstroShine has **no login at all** (SECURITY.md). Under HA,
   ingress puts the HA login in front of it; the direct port does not. See 5.6.

---

## 2. How the apps repository works

Repo `myastroboard/home-assistant-apps` (HA renamed "add-ons" to "apps"). Nothing is
built there: each app wraps the image already published on Docker Hub.

```
repository.yaml
myastroboard/
  config.yaml      # the app manifest
  apparmor.txt     # custom profile (+1 security rating)
  DOCS.md          # "Documentation" tab in HA
  README.md        # store card
  CHANGELOG.md     # filled by the bot
  icon.png logo.png
scripts/update_apps.py
.github/workflows/update-apps.yml   # hourly, opens/refreshes PR bot/update-apps
.github/workflows/lint.yml          # frenck/action-addon-linter per app + dry-run of the script
```

### 2.1 Version bump bot

`scripts/update_apps.py` is generic, nothing to change to add MyAstroShine:

- reads `version:`, `url:` (upstream GitHub repo), `image:` (Docker Hub), `arch:` from
  each `<app>/config.yaml`;
- takes the newest **GitHub release** (not just a tag; drafts and pre-releases ignored)
  newer than `version:` **whose Docker Hub tag has every declared arch** (never point
  users at a tag they cannot pull);
- rewrites `version:` and prepends the notes from upstream `CHANGELOG.md` at that tag.
  At tag time the notes are still under `## [Unreleased]` (the post-release PR archives
  them later) - the script reads `## [Unreleased]` or `## [x.y.z]` / `## x.y.z (date)`,
  so MyAstroShine's `## [0.4.2] - date` style works. Relative links are rewritten to
  absolute GitHub URLs (they would be dead in HA).
- Opens a PR (needs the `GH_PAT` secret so the PR triggers the lint checks).

MyAstroShine: release.yml already uses `softprops/action-gh-release` (a real release)
and publishes `myastroboard/myastroshine` for amd64 + arm64. Just check the release is
created **after** the Docker Hub manifest is pushed, or the bot simply waits one more
hour (harmless).

### 2.2 The board's final `config.yaml` (template)

```yaml
name: MyAstroBoard
version: "1.6.8"            # managed by the bot - must match a Docker Hub tag
slug: myastroboard
description: ...
url: https://github.com/myastroboard/myastroboard
image: myastroboard/myastroboard
arch: [amd64, aarch64]      # HA name aarch64 == Docker arm64
stage: experimental
ingress: true
ingress_port: 5000
panel_icon: mdi:telescope
panel_title: MyAstroBoard
ports:
  5000/tcp: 5000
ports_description:
  5000/tcp: Direct access (installable app, notifications, Astrodex stream)
environment:
  DATA_DIR: /data
  MYASTROBOARD_HA_INGRESS: "1"   # opt-in trust of X-Ingress-Path, never set on plain Docker
timeout: 20                       # seconds HA waits for a clean stop (default 10)
backup_exclude:
  - "cache/**"
  - "*.log"
  - "*.log.*"
```

Decisions behind it (user's, keep them unless told otherwise):

- **Prebuilt Docker Hub images**, not ghcr, not built by HA.
- **No app options** (`options:`/`schema:`): everything is configured in the web UI and
  persisted in `/data`. Same philosophy as MyAstroShine's "no .env editing".
- **No MQTT auto-config / no `services:`**: optional connectors stay optional.
- No `webui:` once ingress is on ("Open web UI" then opens the panel).
- No `watchdog:` / `startup:` in the end: the image `HEALTHCHECK` is what HA uses.

### 2.3 Draft for MyAstroShine (to validate)

```yaml
name: MyAstroShine
version: "0.4.2"
slug: myastroshine
description: Astronomical image enhancement and stacking
url: https://github.com/myastroboard/myastroshine
image: myastroboard/myastroshine
arch: [amd64, aarch64]
stage: experimental
ingress: true                 # only once the image supports it (section 5)
ingress_port: 8002
panel_icon: mdi:image-filter-hdr
panel_title: MyAstroShine
ports:
  8002/tcp: null              # see 5.6: disabled by default? or 8002
environment:
  APP_ENV: production
  DATA_DIR: /data
  PROCESSING_MODE: sync       # single container: no worker, no Redis
  MYASTROSHINE_HA_INGRESS: "1"
timeout: 30                   # sync processing may be running at stop time (3.4)
backup_exclude:
  - "images/**"
  - "stacks/**"
  - "cache/**"
  - "*.log"
  - "*.log.*"
map:
  - share:ro                  # external engines, see 3.5 (only if we support them)
```

Open point: `backup_exclude` of `images/**` / `stacks/**` assumes they are working
copies that expire anyway (`session_expiry_hours`). If a user expects a stack in
progress to survive a restore, say so in DOCS.md.
SQLite in `/data/db`: HA does hot backups by default (files copied while the app runs).
The board uses JSON files and never had to care; MyAstroShine should decide between
`backup: cold` (app stopped during backup - simplest and safe) or accepting the tiny risk.

---

## 3. Container / image fixes (code side)

### 3.1 Single container = no beat = no cleanup (MyAstroShine specific, blocker)

In compose, `worker` runs Celery with `-B`, and beat runs `task_cleanup_sessions`
hourly (sessions + stacks + stale jobs). An HA app is **one container**: no worker, no
Redis, so the cleanup never runs and `/data` grows without limit (and HA backups with it,
unless excluded).

Fix upstream before the app exists, e.g. in `lifespan()`: when
`processing_mode == "sync"`, start an asyncio task that calls the same cleanup code
every hour (in a thread, `asyncio.to_thread`), cancelled on shutdown. Keep beat as the
single owner in queue mode so the two never both run.

Also make sure `import celery`/`redis` at startup does not try to connect anywhere in
sync mode (quick check: start the image with only `PROCESSING_MODE=sync`, no Redis, and
read the logs).

### 3.2 Old x86 CPUs: rebuild NumPy (and check OpenCV)

What happened: the HAOS VM on Proxmox used CPU type `kvm64` (community-script default).
MyAstroBoard crashed at `import numpy`: PyPI NumPy 2.5.x wheels require x86-64-v2
(SSE4.2/POPCNT). Exit code 132 (SIGILL), no Python traceback.

Board fix (Dockerfile, amd64 only):

```dockerfile
ARG REBUILD_FOR_OLD_CPUS="numpy"
RUN if [ "$TARGETARCH" = "amd64" ]; then \
      for pkg in $REBUILD_FOR_OLD_CPUS; do \
        ... find /wheels -iname "numpy-*.whl" -delete; \
        pip wheel --no-cache-dir --no-binary numpy --no-deps --wheel-dir /wheels \
          "numpy==${version}" \
          -Csetup-args=-Dcpu-baseline=none -Csetup-args=-Dallow-noblas=true; \
      done; \
    fi
```

Pitfalls we hit:
- `cpu-baseline=min` is **not** enough: NumPy's `min` is X86_V2 now. Use `none`.
  NumPy still dispatches SSE4/AVX2/AVX-512 kernels at runtime on CPUs that have them.
- `--no-cache-dir` is mandatory: pip's wheel cache ignores `-C` settings and silently
  reuses a wheel built with other options.
- Needs `gcc g++` in a **builder** stage (the board builds wheels in a builder stage;
  MyAstroShine installs straight into the runtime stage, so a builder stage for
  Python wheels has to be added, or the compiler removed after the build).

MyAstroShine specifics: besides `numpy`, **`opencv-python-headless`**, `astropy`,
`rawpy` and `Pillow` ship native code. Do not guess - test. The board has a CI gate for it:
`scripts/check_cpu_compat.sh <image>` runs `scripts/cpu_compat_smoke.py` under
`qemu-x86_64 -cpu kvm64` **inside the built image**, imports every native package, and
names the culprit (exit 132 + native dependency check). Wired in
`.github/workflows/cpu-compat.yml` (PRs touching requirements/Dockerfile) and as a job
of the release workflow between build and manifest publish. Copy both scripts and adapt
the import list. Board policy (CONTRIBUTING.md "CPU compatibility"): on a failing
dependency bump, default = dependabot ignore; rebuild from source only when needed.
Rebuilding OpenCV from source would be very long - if it is an offender, prefer pinning.
Verified on the board: identical numerics under kvm64, only big matmul slower.

### 3.3 Listen on IPv6 too

What happened: HA's "Open web UI" link uses the host name the browser used for HA;
`homeassistant.local` resolved to an IPv6 link-local address (`fe80::...`), and
gunicorn only listened on `0.0.0.0` -> unreachable.

Board fix: `gunicorn.conf.py` binds `[::]:5000` (dual stack) and falls back to
`0.0.0.0:5000` when IPv6 is disabled in the kernel (`/proc/net/if_inet6` missing), and
binds both when `bindv6only=1`.

MyAstroShine: `CMD ["uvicorn", ..., "--host", "0.0.0.0", ...]`. Changing it to `--host ::`
needs a test, not an assumption: asyncio's `create_server` sets `IPV6_V6ONLY` on IPv6
sockets it creates itself, so `--host ::` may end up **IPv6-only** and lose IPv4 (the
HEALTHCHECK on `localhost` and every IPv4 client). Check with the built image:
`curl http://127.0.0.1:8002/api/health` **and** `curl -g "http://[::1]:8002/api/health"`.
If IPv4 is lost, create the socket yourself (dual stack, `IPV6_V6ONLY=0`) and pass it
with `uvicorn --fd`, or run uvicorn from a small Python launcher that does the same, with
the IPv4-only fallback of the board.

Consequence to remember for section 5: with a dual-stack socket, IPv4 peers show up as
**`::ffff:172.30.32.2`** (IPv4-mapped IPv6). That broke the board's ingress (7.1).

### 3.4 Clean stop (exit 0, within `timeout:`)

What happened: HA showed the board as "Error" after a normal Stop.
- `entrypoint.sh` used `su`: `su` stayed the parent, got SIGTERM, killed gunicorn and
  exited 143 -> HA reports a failure. Fix: `exec setpriv --reuid=appuser --regid=appuser
  --init-groups -- "$@"` (setpriv *becomes* gunicorn, which gets SIGTERM itself). setpriv
  does not set `HOME`, gunicorn needs it for its control socket: `export HOME=/home/appuser`.
- Background threads (cache updater, MQTT "offline" message) delayed the stop past HA's
  10 s default -> SIGKILL. Fix: bounded joins (3 s each) + `timeout: 20` in config.yaml.
  Result: stop in ~3 s, exit 0.

MyAstroShine: uvicorn is PID 1 in exec form and runs as root, so the `su` trap does not
apply (remember it if a non-root user is ever added: use `setpriv`, never `su`).
What remains to check: a **sync** processing or stacking request running when HA stops
the app. uvicorn waits for in-flight requests (unbounded unless
`--timeout-graceful-shutdown N`), HA kills at `timeout:`. Pick
`--timeout-graceful-shutdown` < `timeout:` and verify exit code 0 with a long stack in
progress. Open WebSockets are closed by uvicorn on shutdown (the client reconnects with
backoff when the app is back).

### 3.5 External engines (`/opt/engines`)

Compose bind-mounts `./engines:/opt/engines:ro`. HA apps cannot bind arbitrary host
folders; they get `map:` entries: `share` (-> `/share`), `addon_config` (-> `/config`,
per-app folder), `media`, ... Options:
- `map: [share:ro]` and document "put the binary in `/share/myastroshine/engines/...`
  (Samba / File editor) and set that path in Settings -> Advanced";
- or declare engines unsupported in the HA app for now (simplest, say it in DOCS.md).
Also: an engine binary downloaded for x86 will not run on aarch64 HA hosts. And
AppArmor must allow executing it (the broad `file,` rule does, see section 4).

### 3.6 `.dockerignore`

The board's `.dockerignore` was itself gitignored by mistake, so local builds baked
nested `backend/*/.mypy_cache` into the image. MyAstroShine's repo has `backend/data/`,
`backend/test-results/`, `tmp/images test/*.fit`, `frontend/node_modules`... Check the
`.dockerignore` exists, is committed, and that `docker build` context stays small.

### 3.7 Logs

The board made log levels editable in the UI at runtime (Parameters -> Log export) because
an HA user cannot set env vars like `LOG_LEVEL`. The app's **Log** tab in HA is the
container stdout. MyAstroShine already has `apply_runtime_log_levels()` and a log export
endpoint: only document where to find them in DOCS.md.

---

## 4. AppArmor

### 4.1 Why

HA shows a security rating per app: base 5, **max 6**. A custom `apparmor.txt` gives +1,
`ingress: true` gives +2 - but capped, so AppArmor alone reaches 6. Ingress is for the
UX (and, for MyAstroShine, security - see 5.6), not the score. `auth_api` is useless for
us. Anything like `host_network`, `full_access`, `privileged`, `docker_api` costs points.

### 4.2 The board profile (final, clean in complain AND enforce)

`home-assistant-apps/myastroboard/apparmor.txt`:

```
#include <tunables/global>

profile myastroboard flags=(attach_disconnected,mediate_deleted) {
  #include <abstractions/base>

  # entrypoint.sh: chown -R on /data, then setpriv to appuser
  capability chown,
  capability fowner,
  capability dac_override,
  capability dac_read_search,
  capability setuid,
  capability setgid,
  capability kill,

  network inet stream,
  network inet6 stream,
  network inet dgram,
  network inet6 dgram,
  network netlink raw,

  signal (send, receive) peer=@{profile_name},
  signal (receive) peer=unconfined,

  file,

  deny mount,
  deny umount,
  deny pivot_root,
  deny ptrace,
  deny capability sys_admin,
  deny capability sys_module,
  deny capability sys_rawio,
  deny capability net_admin,
  deny capability sys_ptrace,
  deny network inet raw,
  deny network inet6 raw,
  deny network packet,
  deny /proc/sys/kernel/** w,
  deny /sys/** w,
}
```

Lessons:
- **`@{profile_name}`, never the literal name**: the Supervisor rewrites the profile
  name to the installed slug (`ff6fddf1_myastroboard`, `local_myastroboard_dev`, ...);
  a hardcoded `peer=myastroboard` stops matching.
- `signal (receive) peer=unconfined` is what lets Docker/Supervisor deliver SIGTERM.
- **`deny network raw` (bare) also cancels `network netlink raw`**: deny rules win.
  Deny `inet raw` / `inet6 raw` only.
- Broad `file,` + targeted denies (HA template style): a tight path list can come later
  once logs show the real paths. `file,` also covers the `curl` HEALTHCHECK exec.

### 4.3 MyAstroShine adaptation

- Runs as root, no `chown`/user switch at start: drop `chown`, `fowner`, `setuid`,
  `setgid` (and probably `dac_override`/`dac_read_search`) - then **prove it in complain
  mode**; keep a capability if the log shows it.
- Outbound network: AstroDex callbacks (httpx), GitHub release check -> inet/inet6 stream + dgram (DNS).
- `subprocess` is used (`engine_probe.py`, `external_engine.py`): external engines are
  executed; with `file,` it works, exercise it during the complain run if engines are supported.
- `capability kill` / signals: uvicorn single process; keep the signal rules as is.

### 4.4 Test procedure on HAOS (what actually worked)

1. Dev copy of the app in **local apps**: Samba share `addons` == `local_apps` (store
   apps are not visible over Samba, normal). E.g. `\\HOMEASSISTANT\addons\myastroshine_dev\`
   with slug `myastroshine_dev`, another host port, `apparmor.txt` with
   `flags=(attach_disconnected,mediate_deleted,complain)`.
2. **No `image:`** in the dev config.yaml, and a one-line `Dockerfile`:
   `FROM myastroboard/myastroshine:0.4.2`. With `image:`, the Supervisor pulls
   `image:version` and a `-dev2` version gives a 404.
3. Reload the profile = **bump version (`0.4.2-dev2`, `-dev3`...) + Update**. Never
   uninstall to "reload": uninstall wipes `/data`.
4. Exercise every I/O feature (upload, process sync, stack, star mask, auto astro,
   AstroDex handoff round-trip, download, log export, presets, settings save, engines,
   stop/start).
5. Read the AppArmor log. **Not in dmesg on HAOS** (audit subsystem). From the SSH app:
   `ha host logs --identifier audit --lines 50000 | grep -i apparmor > /share/x.log`,
   then open `/share/x.log` over Samba. Look for `apparmor="DENIED"` / `"ALLOWED"`
   (complain mode logs ALLOWED for what enforce would deny).
6. Remove `complain`, bump version, repeat 4-5 in enforce mode. Board result: zero
   DENIED/ALLOWED in both runs.
7. Copy the final profile into the real app folder; it ships with the next bot bump.

"Unknown error" when reloading the store = HA core's 10 s timeout while the Supervisor
git-pulls every repository. Harmless, retry.

---

## 5. Ingress

### 5.1 How it works (verified on a real instance)

- The browser loads `https://<ha>/api/hassio_ingress/<token>/...` inside an iframe of the
  HA frontend. Sidebar URL is `/<slug>` (e.g. `/ff6fddf1_myastroboard`), "Open web UI" is
  `/app/<slug>`. The token is stable per install.
- The Supervisor proxies to `http://<container>:<ingress_port>/<rest>`, **prefix stripped**,
  and adds `X-Ingress-Path: /api/hassio_ingress/<token>`, `X-Forwarded-For` (HA core's
  hop appended), `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Remote-User-*`.
- TCP peer is always the Supervisor, **`172.30.32.2`** - which gunicorn/uvicorn on a
  dual-stack socket reports as **`::ffff:172.30.32.2`**.
- Same origin as HA for every app: any root-absolute URL (`/api/...`, `/assets/...`)
  escapes the prefix and hits **Home Assistant's own** `/api` -> 404/401. That is the
  whole difficulty.
- WebSockets are proxied too.

### 5.2 What the board built (for reference)

Backend - `backend/utils/ingress.py` in myastroboard, worth reading in full:

- `IngressMiddleware` (WSGI, outermost): honors `X-Ingress-Path` **only if** env flag
  `MYASTROBOARD_HA_INGRESS` is set (the HA app sets it, Docker installs never do) **and**
  the TCP peer is the Supervisor. Otherwise the header is dropped (the direct port is
  public: anyone could send it). Then:
  - validates the prefix (`^(/[A-Za-z0-9._~-]+)+$`, it ends up in HTML/JS/cookie Path),
    sets `SCRIPT_NAME`; tolerates a proxy that did not strip it;
  - **restores the client IP**: rightmost `X-Forwarded-For` hop **outside
    `172.30.32.0/23`** (HA core 172.30.32.1 and the Supervisor append themselves; left
    of them is browser-controlled and spoofable);
  - scheme/host from `X-Forwarded-Proto/Host`;
  - removes the `X-Forwarded-*` it consumed so an inner ProxyFix does not re-apply them;
  - `_parse_ip()` **unwraps IPv4-mapped IPv6** for the peer and every XFF hop (7.1).
  - Test hook: `MYASTROBOARD_HA_INGRESS_PROXY_IP` overrides the trusted peer for a local
    fake proxy.
- Session cookie renamed/path-scoped **only under ingress** (all ingress apps share the
  HA origin; Flask's default `session` would collide). Direct-port sessions unchanged.
- `external_base_url()`: admin setting "External base URL" (Parameters -> Advanced) for
  URLs consumed by **other software** (Astrodex stream for HA camera/Lovelace card,
  MyAstroShine callback). Under ingress there is no usable request-derived URL (it needs
  an HA login), so it refuses with a clear message when the setting is empty.

Frontend:
- Templates: `{{ base }}` Jinja global (= `request.script_root`) on every src/href, and
  `<meta name="app-base">`.
- `api_helper.js` loads first: `appUrl(path)` (idempotent prefixer) + **one global
  `window.fetch` wrapper** when a prefix is set, instead of patching ~100 call sites.
- CSS `url()` made relative (`../img/...`).
- PWA/service worker/manifest/push disabled under a prefix, documented for users.

Guard: `tests/test_base_path_urls.py` scans JS, templates and CSS and fails on any new
root-absolute URL outside the safe helpers. Without it the next feature breaks ingress
silently - CI never runs under a prefix.

### 5.3 Why MyAstroShine needs far less

- Hash routing: `location.pathname` is always the app root (`/` or
  `/api/hassio_ingress/<token>/`). So **relative URLs just work**, no server-side prefix
  injection is needed at all.
- No templates, no cookies, no service worker, no manifest.
- The backend builds no absolute URL for the browser (checked: no `url_for` /
  `request.url` / `base_url` in `backend/app`). `callback_base` comes from the board.
- `X-Frame-Options: SAMEORIGIN` (main.py) is fine: the HA page and the ingress iframe
  share the origin. **Do not switch it to `DENY`** or add CSP `frame-ancestors 'none'`,
  that would blank the panel.

### 5.4 Frontend changes (all of them, as far as grep shows)

| Where | Today | Under a prefix | Change |
|---|---|---|---|
| `vite.config.ts` | default `base: '/'` -> built `index.html` loads `/assets/...` | escapes -> blank page | `base: './'` (Vite also rewrites `/favicon.svg` in index.html) |
| `src/services/api.ts:43` | `VITE_API_URL ?? '/api'` | escapes | default to a path relative to the page: e.g. `new URL('api', document.baseURI)` pathname, or `'./api'` |
| `src/services/ws.ts:18` | `` `${scheme}//${host}/ws` `` | escapes | include the page directory: `` `${scheme}//${host}${dirOf(location.pathname)}ws` `` |
| `src/App.tsx:139` | `src="/logo.png"` (JSX, not rewritten by Vite) | escapes | `` `${import.meta.env.BASE_URL}logo.png` `` or import the asset |
| `App.tsx:82` | `replaceState(..., `${location.pathname}#/`)` | OK | nothing |
| downloads (`api.ts` fetch + blob) | via `API_URL` | OK once API_URL is fixed | nothing |

Keep `VITE_API_URL` / `VITE_WS_URL` overrides working for dev (Vite dev server proxies
`/api` and `/ws`, served at `/`, so relative URLs work there too).

Then add the guard: a vitest (or pytest) test that scans `frontend/src` (non-test files)
for `'/api`, `"/api`, `` `/api ``, `/ws`, `src="/`, `href="/` literals and fails.
Also build once and scan `frontend/dist/index.html` + `dist/assets/*.css` for `"/assets/`
and `url(/` - **the board's static scans missed CSS `url(/static/...)` and an inlined
SVG `href`; only the proxied browser walk (5.7) found them.**

### 5.5 Backend changes

No `root_path` handling is required for routing (the Supervisor strips the prefix and
the SPA uses relative URLs). What is required: **the client IP**.

`app/utils/rate_limit.py:get_client_ip()` uses `request.client.host`, and the per-IP
limits are "N requests/minute" and **"5 concurrent processing jobs per IP"**
(`JobService.assert_under_concurrency_limit`). Under ingress every HA user has the
Supervisor's IP: one user stacking 5 jobs blocks every other user, and the rate limit is
shared by everybody. The board had exactly this risk for login throttling.

Port the board's middleware as a **pure ASGI middleware** (it must cover both `http` and
`websocket` scopes):

- enabled only by `MYASTROSHINE_HA_INGRESS=1` (env, set by the HA app) - keep it
  independent from any generic proxy setting;
- trusted only if `scope["client"][0]`, IPv4-mapped unwrapped, == `172.30.32.2`
  (override env var for local tests);
- else strip `x-ingress-path` and do nothing else;
- if trusted: `scope["client"] = (rightmost XFF hop outside 172.30.32.0/23, port)`,
  optionally `scope["root_path"] = prefix` (validated) for logs/future absolute URLs,
  `scope["scheme"]` from `X-Forwarded-Proto`.

Do **not** simply add `uvicorn --proxy-headers --forwarded-allow-ips=172.30.32.0/23`
without testing it: it is not gated by the HA flag, and whether it matches a
`::ffff:172.30.32.2` peer must be proven, not assumed (see 7.1).

### 5.6 Direct port and the no-auth problem (decision needed)

MyAstroShine has no login ("anyone who can reach the API is trusted", SECURITY.md).

- Through ingress, HA authentication is in front: only HA users reach it. This is the
  best security MyAstroShine can get without writing an auth system.
- The direct port bypasses that: anyone on the LAN can use the app and its admin
  settings. HA's recommended setup is `ports: 8002/tcp: null` (declared, disabled by
  default, the user opts in from the app's Network section).

What needs the direct port / a non-ingress URL:
- **MyAstroBoard -> MyAstroShine browser handoff**: the board opens MyAstroShine in a new
  tab with `#/?handoff=...`. An ingress URL opened outside the HA frontend works only if
  the browser still holds HA's `ingress_session` cookie - fragile, **to test**; otherwise
  the handoff needs the direct port.
- **Server-to-server** (MyAstroShine pulls the source image from the board and posts the
  enhanced one back to `callback_base`): if both are HA apps, they reach each other on the
  internal `hassio` network by hostname (`<repo-hash>-<slug with - instead of _>`, e.g.
  `ff6fddf1-myastroboard:5000`; check with `ha apps info <slug>` / `ha addons info`),
  **without any published port**. The board's `callback_base` comes from its "External
  base URL" setting (required under ingress), so that setting must be something the
  MyAstroShine container can reach, and it must be on MyAstroShine's
  `astrodex_callback_urls` allowlist.
  Note: a request from another container has no `X-Ingress-Path`, so the board's
  middleware leaves it alone - no conflict.

Proposal: `null` by default + DOCS.md section "Using MyAstroShine from MyAstroBoard"
explaining when to enable the port. Confirm with the user.

### 5.7 How we tested ingress without HA (and why it was not enough)

- Local fake Supervisor: a small aiohttp proxy stripping `/api/hassio_ingress/test/`,
  adding `X-Ingress-Path` + `X-Forwarded-*`, app started with the "trusted proxy IP"
  override. Then a **Playwright walk of every tab** logging any request that escaped the
  prefix: that walk is what found the CSS and SVG misses. Scripts were throwaway
  (`run_app.py`, `fake_supervisor.py`, `walk_ingress.py`); worth committing a version of
  them in MyAstroShine's `frontend/e2e/` this time.
- **What it missed**: the fake proxy connected over IPv4 to an IPv4 socket, so
  `REMOTE_ADDR` was `127.0.0.1`/`172.30.32.2`. On real HA it is `::ffff:172.30.32.2` ->
  1.6.7 shipped broken (7.1). **Always test the dual-stack peer form** (bind the app on
  `::` and connect the proxy through `127.0.0.1`, peer then shows `::ffff:127.0.0.1`).

### 5.8 Shipping order (important)

`ingress: true` in `config.yaml` must never reach users before an image that supports it:
1. MyAstroShine release X with sub-path support.
2. The bot bumps `version:` to X (PR merged).
3. Only then commit `ingress: true` + the DOCS.md rewrite **together** (DOCS.md describes
   the panel; shipping it earlier documents a feature users do not have).

---

## 6. Test on a real HA instance

The user's HA is a **test** instance (production runs plain Docker), HAOS VM on Proxmox.

Checklist used for the board, adapted:
- Install from the store, Start, wait: **the app card takes several seconds to show
  "started"; clicking Start again stops it** (we chased a phantom "stops right after
  start" bug for this - Supervisor log showed an explicit "Stopping"). Say it in DOCS.md.
- Open via sidebar and "Open web UI"; also `http://homeassistant.local:<port>` (IPv6!)
  and `http://<ip>:<port>` if the port is enabled.
- Every tab/feature through the panel; watch the browser network panel for 404s on
  `/api/...` without the ingress prefix.
- **Large uploads and long sync requests through ingress** (stack archives, many frames):
  body size and proxy timeouts of the Supervisor are unknown for our sizes - measure.
  Measured on MyAstroShine: without `ingress_stream: true` the Supervisor reads the
  body whole (`await request.read()`) and refuses anything over 16 MiB ("Maximum
  request body size 16777216 exceeded"). With it, POST bodies are streamed (other
  methods are still read whole). Its proxy timeout is `total=None`.
  A Cloudflare tunnel / proxied domain in front of HA caps a body at 100 MB (Free/Pro):
  the upload hangs "pending" for a while, then Cloudflare answers an HTML 413. Engine
  packages (200-300 MB) only install from the local address; documented in DOCS.md.
- WebSocket progress through ingress.
- Two HA users (or two browsers) at once: rate limit / concurrent-job limit is per user.
- HA companion app on mobile, and remote access (Nabu Casa / remote URL) if available.
- Stop: ~seconds, exit code 0, no "Error" state. Restart. Update (bump) keeps `/data`.
- Backup + restore of the app.
- AppArmor enforce: no DENIED in the audit log after all of the above.
- Log the real ingress headers once at DEBUG (never log the token-bearing prefix at INFO).

---

## 7. Traps we fell into

### 7.1 IPv4-mapped IPv6 peer (1.6.7 -> 1.6.8)

gunicorn on `[::]:5000` reported the Supervisor as `::ffff:172.30.32.2`; the code compared
the string to `172.30.32.2`, rejected every ingress request -> 404 on every page on real
HA, while every local test passed. Fix: parse with `ipaddress`, unwrap `.ipv4_mapped`,
compare addresses, same for each XFF hop. Rule: **never compare IPs as strings**.

### 7.2 Static scans are not enough

grep/regex scans of JS and templates missed a CSS `url(/static/...)` and an inlined SVG
`href`. Only a real browser behind a prefix proxy catches everything. Do both.

### 7.3 Things that looked like app bugs but were HA

- "Stops right after first start": double click on Start (see 6).
- "Unknown error" on store reload: HA core timeout while the Supervisor git-pulls repos.
- AppArmor "no denials" in `dmesg`: they are in the **audit** log, not the kernel log.
- Dev copy 404 on pull: `image:` + a `-devN` version.
- Store apps invisible over Samba: only local apps (`addons` share) are.

### 7.4 Version / release plumbing

- The bot needs a PAT (`GH_PAT`), not `GITHUB_TOKEN`, or its PR does not trigger checks.
- Notes are taken from `## [Unreleased]` at the tag, because the changelog is archived
  by a post-release PR. If MyAstroShine archives before tagging, the `## [x.y.z]` heading
  is used instead - both work.
- Earlier the bot committed straight to main; changed to a PR (bot/update-apps).

### 7.5 Misc

- HA linter (`frenck/action-addon-linter`) runs in CI per app folder; keep config.yaml
  minimal (we removed `startup`/`watchdog` it complained about or that were redundant).
- `timeout:` in config.yaml defaults to 10 s - too short for apps with background work.
- Exit code 143 on stop shows as an error on the app card ("did not handle SIGTERM").
  uvicorn >= 0.29 re-raises the caught SIGTERM after its graceful shutdown; MyAstroShine
  drops it (`app.serve.Server`). Check with `docker run --init` + `docker stop` + the
  `ExitCode` from `docker inspect`, not with the logs (they look clean either way).
- `stage: experimental` while the app is young.
- Docs for end users go in the app's `DOCS.md` (HA "Documentation" tab); link to the
  upstream docs for the rest. Keep the upstream README's "Home Assistant app" install
  section in sync.

---

## 8. Proposed order of work

MyAstroShine repo (each item = a release note line under `## [Unreleased]`):

1. Sync-mode cleanup scheduler (3.1). Blocker for any single-container install, HA or not.
2. CPU compat: smoke test under `qemu -cpu kvm64`, then NumPy rebuild (+ others if the
   test names them), CI gate (3.2).
3. Dual-stack listen, verified for IPv4 + IPv6 (3.3); graceful shutdown bound (3.4);
   `.dockerignore` check (3.6).
4. Release. Then create `home-assistant-apps/myastroshine/` **without ingress**: config.yaml,
   README.md, DOCS.md, CHANGELOG.md, icon.png, logo.png, apparmor.txt (complain -> enforce
   on the HA test instance, section 4.4). The bot picks it up from there.
5. Ingress support in MyAstroShine: frontend relative URLs + guard test (5.4), ASGI
   client-IP middleware + tests incl. `::ffff:` peers and spoofed headers from a
   non-Supervisor IP (5.5), local prefix-proxy Playwright walk (5.7). Release.
6. After the bot bumped to that release: `ingress: true` + panel fields + DOCS.md rewrite,
   port default decision (5.6), in one commit.
7. MyAstroBoard <-> MyAstroShine both as HA apps: handoff + callback over the internal
   hostnames, documented in both DOCS.md.
