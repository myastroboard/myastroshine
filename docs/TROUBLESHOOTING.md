# Troubleshooting

Common problems and what to check. If something here doesn't cover it, export the
logs (**Settings -> Logs -> Export**) and open a
[bug report](https://github.com/myastroboard/myastroshine/issues/new/choose).

## Contents

- [Processing and the editor](#processing-and-the-editor)
- [Uploads](#uploads)
- [Stacking](#stacking)
- [External ML engines](#external-ml-engines)
- [Queue mode and the worker](#queue-mode-and-the-worker)
- [Settings and CORS](#settings-and-cors)
- [Development](#development)
- [Logs](#logs)

## Processing and the editor

**The preview doesn't update / I have to click twice / it froze during a slider
drag.** Fixed in the current build. Preset apply, Auto Astro and re-stacking now
follow the job to completion; the editor keeps at most one `/process` in flight
per session and coalesces the rest; and the progress WebSocket no longer holds a
pooled DB connection (a burst of sockets used to exhaust the pool - see
"`QueuePool limit ... connection timed out`" below). If you still see a stale
preview on an older build, a hard refresh (Ctrl/Cmd-Shift-R) clears the browser's
cache of the preview URL.

**The API log shows `QueuePool limit of size 5 overflow 10 reached, connection
timed out` and `/process` returns 500.** The database connection pool was
exhausted - on older builds the progress WebSocket held a connection open for its
whole lifetime, so a burst of edits (one socket per queued job) starved every
other request. Fixed in the current build. If you see it on an older one,
restarting `api` clears the stuck connections; upgrade to stop it recurring.

**"Too many concurrent processing jobs" (429).**
The per-IP concurrent-job cap (`max_concurrent_jobs_per_ip`, default 5) was hit -
usually several stacks or re-stacks in flight at once, or a shared household IP.
Raise it in **Settings -> Advanced**, no restart needed. A burst of slider moves
can't cause this (a new edit retires the previous pending job for that session).

**"Rate limit exceeded" (429) during normal editing.**
`rate_limit_per_minute` (default 600) is a shared 60-second window across
`/upload`, `/process`, preset apply, `/star-mask`, `/auto-astro`, and `/stack/*`.
One person doing real work should never reach it; raise it in
**Settings -> Advanced** for a shared IP, or turn the limiter off there.

**The depth map looks like a flat gradient with no stars.**
The depth estimate is gradient-based (detail = near, smooth sky = far). On a
low-detail target - a smooth nebula with few stars - there is little gradient to
work with, so the parallax is subtle. Pick a focal point on the preview to pull
that region forward. ML depth models were evaluated and rejected for starfield
content (see [ALGORITHMS.md](ALGORITHMS.md#depth-map)).

**A slider seems to do nothing.**
`depthShiftIntensity` currently has no effect - it is a known dead parameter (see
the changelog's "Known gaps"). The Depth Shift viewer has its own intensity
control. Every other slider is live.

## Uploads

**"Unsupported format" (415) on a file that should work.**
Check the extension is one of the supported list
([FEATURES.md](FEATURES.md#uploading)). A FITS file with an empty primary HDU is
fine (the first HDU *with data* is used). A raw one-shot-colour FITS *mosaic*
from a stacking tool is out of scope for the single-image upload - stack it in
the Stacking mode instead, or export a debayered TIFF.

**"File too large" (413).**
Over `max_image_size_mb` (default 100, the compressed byte size) or over the
decoded-pixel-count cap (a decompression-bomb guard). Raise
`max_image_size_mb` in **Settings -> General** for genuinely large frames.

**A FITS or 16-bit TIFF comes out far too bright.**
That auto-stretch assumes *linear* data (a raw stack). If the file is already a
*finished*, non-linear export, the stretch over-brightens it - re-export it as
8-bit, or undo the stretch with the tone controls.

**Colours look rebalanced after a FITS / RAW upload.**
Each channel is stretched independently on ingest, which also auto-balances each
channel's black level. If the source was already colour-calibrated, correct it
with the **Background** step's temperature / tint, or the **Curves** step.

## Stacking

**"At least 2 frames are required to stack."**
Fewer than two frames are included. Check the frame grid - auto-rejected frames
count as excluded. Uncheck one to rescue it, or lower the quality-filter strength
in the **Settings** step and re-stack.

**Many frames rejected as `trailed` / `soft` / `clouds` / `bright_sky`.**
The quality filter is relative to the set's own median. If a whole session was
marginal, `moderate` can reject most of it - set it to `lenient` or `off` in the
Stacking **Settings** step and re-stack. Individual rescues (uncheck a frame) are
remembered across runs.

**The stack failed with "processing was interrupted."**
A previous run was killed (container restart, OOM) and left a checkpoint behind;
the hourly cleanup marks it failed and reclaims the ~13 GB align memmap after 30
minutes. Just run it again.

**Re-stacking is slow even when I only changed the combination method.**
It should resume from the aligned frames if you changed *only* the combination /
rejection / weighting / drizzle and the last run was within ~30 minutes.
Changing the registration transform, calibration, or the frame selection forces
a full re-align.

**Registration failures / the target drifts to a corner.**
Asterism matching needs enough real stars per frame. A frame that fails to match
is dropped and counted in `frames_excluded`. Very sparse frames, heavy trailing,
or a wildly different pointing won't align. The reference is picked near the
session's temporal middle to keep the common footprint centred.

## External ML engines

**The StarNet2 / DeepSNR toggle doesn't appear in the editor.**
The engine only shows when its path points at a working binary. In
**Settings -> Advanced -> External ML engines**, check the status line, then
**Re-check engines**:

| Status line | Meaning | Fix |
|-------------|---------|-----|
| "No path configured" | the setting is empty | set the in-container path, e.g. `/opt/engines/starnet2/starnet2` |
| "not found" | the path doesn't resolve inside the container | confirm the file is under `./engines/` on the host and the container was recreated (`docker compose up -d`) |
| "detected" (green) | working | the toggle is now in the Stars / Detail step |
| amber "untested" warning | the binary's version is outside the tested range | it still runs; expect the odd rough edge |

**A pass falls back to the classical engine.**
Any failure - missing binary, non-zero exit, a 15-minute timeout, bad output -
logs a warning and uses the classical code so the edit still completes. Check
`worker.log` (queue mode) or `myastroshine.log` (sync mode) for the reason.
There is no linux-arm64 build of these tools - an ARM host can't use them.

**Nothing to install here is shipped by MyAstroShine.** Download the linux-x64
CLI from `starnetastro.com` yourself and accept its licence -
[THIRD_PARTY.md](../THIRD_PARTY.md), [engines/README.md](../engines/README.md).

## Queue mode and the worker

**Jobs stay "queued" forever (`PROCESSING_MODE=queue`).**
The `worker` isn't running or can't reach Redis. Check `docker compose ps` (the
worker's healthcheck is a real Celery ping), and `docker compose logs worker`.
If Redis is down, jobs queue but never run.

**Progress bar never moves, then the result appears anyway.**
The WebSocket to `/ws/...` couldn't connect (a reverse proxy not forwarding
`Upgrade`, or an ad blocker). Processing still completes; only the live progress
is lost. Proxy the `/ws/` path with WebSocket upgrade headers.

**Expired sessions and stacks aren't being cleaned up.**
The hourly cleanup runs inside the `worker` (Celery beat, `-B`). If you dropped
the worker to run `PROCESSING_MODE=sync`, keep one worker running for the
schedule, or prune the data volume yourself.

## Settings and CORS

**A CORS error in the browser console after changing `cors_origins`.**
The CORS middleware reads `cors_origins` once at startup - restart the `api`
container after changing it. Every other setting applies immediately.

**AstroDex webhook delivery is refused (403).**
`astrodex_callback_urls` is an allowlist that fails closed - an empty allowlist
rejects every callback URL. Add the AstroDex callback origin in
**Settings -> Webhooks** before enabling delivery.

**`ADMIN_ENABLED=false` and Settings won't save.**
That flag disables `/api/admin/*` (and `/api/tokens`) entirely. It is a feature
toggle, not authentication - set it back to `true` (the default) to edit
settings, or edit `app_settings.json` on the volume directly and restart.

## Development

**Images don't load on the Vite dev server (`:3000`), but `fetch` calls work.**
An absolute `VITE_API_URL` makes `fetch` bypass the dev proxy while
`<img src="/api/...">` still uses it. Leave `VITE_API_URL` / `VITE_WS_URL`
**unset** in dev - the app uses same-origin `/api` and `/ws`, and the Vite proxy
(`VITE_PROXY_TARGET`) forwards both to the backend.

**Backend edits aren't picked up in the dev container.**
`docker-compose.dev.yml` sets `WATCHFILES_FORCE_POLLING` so `uvicorn --reload`
sees host edits over the bind mount. The **worker** (watchmedo) can still miss
them - `docker compose -f docker-compose.dev.yml restart worker` after a backend
change is the reliable path. If the editor was already wedged from an older
build, restart `api` too (it clears the exhausted connection pool).

**`pytest` fails on `test_deps_fresh.py`.**
It queries PyPI/npm for stale pins. Offline, it skips itself; to skip it
explicitly, `SKIP_DEPS_FRESH=1 pytest`.

## Logs

- API log: `DATA_DIR/myastroshine.log`; worker log: `DATA_DIR/worker.log`. Both
  rotate (10 MB x 5). The console (`docker compose logs api`) carries the same
  events at `console_log_level`.
- **Settings -> Logs** tails the file, changes the filter level (no restart),
  clears it, and **exports a ZIP** of the log plus its rotations and the worker
  log - attach that ZIP to a bug report.
- Levels: `log_level` (file) and `console_log_level` (console) on the
  **Advanced** tab.
