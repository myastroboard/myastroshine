# MyAstroShine API

Base URL: `http://localhost:8002/api` (configurable via `VITE_API_URL` on the
frontend). Most routes are unauthenticated (local deployment). The AstroDex
handoff routes (`/astrodex/handoff/resume`, `/astrodex/handoff/return`) are
authenticated by the signed handoff token in the request body, not a bearer
header - the token's `kid` selects the webhook token (created in the Settings UI,
`/api/tokens`) whose `signing_secret` verifies it.

## Contents

- [Rate limiting](#rate-limiting)
- [Endpoints](#endpoints)
- [Upload formats](#upload-formats)
- [Processing parameters](#processing-parameters)
- [WebSocket messages](#websocket-messages)
- [Presets](#presets)
- [Depth shift](#depth-shift)
- [Star mask](#star-mask)
- [Auto Astro](#auto-astro)
- [Client config](#client-config)
- [External ML engines](#external-ml-engines)
- [Update check](#update-check)
- [Webhook tokens](#webhook-tokens)
- [AstroDex integration](#astrodex-integration)
- [Stacking](#stacking)

The runtime topology (services, job queue, storage) is in
[ARCHITECTURE.md](ARCHITECTURE.md); the maths behind the parameters is in
[ALGORITHMS.md](ALGORITHMS.md).

All error responses share this shape:

```json
{
  "error": "Human-readable message",
  "error_code": "INVALID_PARAMETER",
  "details": { "parameter": "contrast", "reason": "must be between 0.5 and 3.0" },
  "request_id": "req_abc123",
  "timestamp": "2026-09-03T14:32:31Z"
}
```

Common codes: `INVALID_PARAMETER` (400), `UNAUTHORIZED` (401), `FORBIDDEN` (403),
`NOT_FOUND` / `SESSION_NOT_FOUND` (404), `UNSUPPORTED_FORMAT` (415),
`DUPLICATE_RESOURCE` (400), `PAYLOAD_TOO_LARGE` (413), `SESSION_EXPIRED` (410),
`PROCESSING_FAILED` (500), `ASTRODEX_UNREACHABLE` (503), `RATE_LIMITED` (429).

## Rate Limiting

Per IP, on `/upload`, `/process/{id}`, `/presets/{id}/apply/{session_id}`,
`/star-mask/{id}`, `/auto-astro/{id}`, and `/stack/*`:

- **Requests per minute** (`rate_limit_per_minute`, default **600**): a fixed
  60-second window, shared across all of the routes above (not per-route). Sized
  well above a busy session - the editor re-processes on every slider change
  (500ms debounced, ~120/min on its own) and a stacking upload burst lands on
  top. It is an abuse guard for a public instance, not a fairness mechanism; one
  user doing real work should never hit it (raise it further if a shared
  household IP does).
- **Concurrent processing jobs** (`max_concurrent_jobs_per_ip`, default 5):
  checked against non-terminal rows in the `jobs` table, so it holds under
  both `PROCESSING_MODE=sync` and `queue`. A new `/process` for a session first
  retires (`superseded`) any still-pending job for that same session, so a burst
  of slider edits can't exhaust this budget against itself.

Both settings, plus a `rate_limit_enabled` switch, are editable from
**Settings -> Advanced** (`app_settings.json`, see docs/DEPLOYMENT.md) - no
restart needed. Over either limit returns `429` with `error_code:
"RATE_LIMITED"`.

## Endpoints

Every route is implemented and tested end to end.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | System health |
| GET | `/config` | Public runtime limits (upload cap, stacking limits, engine lists) - no admin gate |
| GET | `/admin/app-settings` | Current runtime settings (`app_settings.json`) |
| POST | `/admin/app-settings` | Replace runtime settings (gated by `ADMIN_ENABLED`) |
| GET | `/admin/engine-status` | Probe the configured StarNet2 / DeepSNR paths |
| GET | `/admin/logs` | Tail the log file, newest first (`limit`, `offset`, `level`) |
| GET / POST | `/admin/logs/level` | Read / change the file and console log levels |
| POST | `/admin/logs/clear` | Empty `myastroshine.log` |
| GET | `/admin/logs/export` | ZIP of the logs (main + rotations + worker) |
| POST | `/upload` | Upload an image, open a session |
| GET | `/preview/{session_id}` | Session image: `?full=true` full-res result, `?original=true` untouched upload (add `&geometry=true` to apply the session's current crop/rotate/flip/straighten, no colour/tone enhancement), default downscaled result. `?v=` cache-buster |
| POST | `/process/{session_id}` | Apply enhancement parameters |
| WS | `/ws/processing-status/{job_id}` | Real-time job progress |
| POST | `/download/{session_id}` | Download the processed image |
| POST | `/depth-shift/{session_id}` | Generate depth map + parallax layers |
| GET | `/depth-shift/{session_id}/metadata` | Depth statistics + layer URLs |
| GET | `/depth-shift/{session_id}/depth_map` | Depth map as a grayscale PNG |
| GET | `/depth-shift/{session_id}/layer_{index}` | Single BGRA layer PNG |
| POST | `/star-mask/{session_id}` | Detect stars in the original image for a mask overlay |
| POST | `/auto-astro/{session_id}` | Analyse the original image and apply a one-click parameter set |
| GET | `/presets` | List presets (5 built-ins + user presets) |
| POST | `/presets` | Save a user preset |
| DELETE | `/presets/{preset_id}` | Delete a user preset (403 for built-ins) |
| POST | `/presets/{preset_id}/apply/{session_id}` | Apply a preset |
| POST | `/stack/initiate` | Open a stacking session |
| POST | `/stack/{stack_id}/upload-frame` | Upload one frame |
| POST | `/stack/{stack_id}/upload-frames` | Upload a batch of frames in one request |
| POST | `/stack/{stack_id}/upload-archive` | Upload a `.zip` of frames in one request |
| POST | `/stack/{stack_id}/frame/{index}/exclude` | Include / exclude a frame (and rescue it from auto-reject) |
| GET | `/stack/{stack_id}/frame/{index}/thumb` | A frame's ~256 px thumbnail |
| POST | `/stack/{stack_id}/calibration/{kind}/frames` | Upload `dark` / `flat` / `bias` / `dark_flat` subs |
| DELETE | `/stack/{stack_id}/calibration/{kind}` | Drop every sub of one calibration kind |
| POST | `/stack/{stack_id}/process` | Align + combine frames (optional body re-stacks with a changed setting) |
| GET | `/stack/{stack_id}` | Stack result, statistics, and the frame list |
| GET | `/stack/latest` | The current folder-watch stack, or `null` |
| WS | `/ws/stack-status/{job_id}` | Real-time stacking progress |
| GET | `/tokens` | List webhook tokens (metadata only) |
| POST | `/tokens` | Create a webhook token (raw value shown once) |
| DELETE | `/tokens/{token_id}` | Revoke a token |
| POST | `/astrodex/handoff/resume` | Open a session from an AstroDex handoff token |
| POST | `/astrodex/handoff/return` | Send the enhanced image back to AstroDex |
| GET | `/version` | The version this instance is running |
| GET | `/version/check-updates` | Latest GitHub release, cached ~4h |

## Upload formats

`POST /upload` and `POST /stack/{stack_id}/upload-frame` accept:

- **8-bit JPEG/PNG/TIFF** - used as-is.
- **FITS** (`.fits` / `.fit` / `.fts`, via `astropy`) and **16-bit PNG/TIFF**
  (e.g. a stacked frame exported from Siril/DeepSkyStacker/PixInsight, or a
  Seestar / ASIAIR live stack) - linear, full-bit-depth data. These open as a
  **composite session** (`is_stack: true` in the response): the 32-bit data is
  kept as `composite.npy`, the field-rotation / vignette border is trimmed, and
  the editor's linear "Stack" step (background extraction, colour calibration,
  tunable deep stretch - see `docs/ALGORITHMS.md`) drives every render. 2D data
  is read as monochrome; a 3-plane array as RGB; a CFA mosaic is debayered.
- **Camera RAW** (`.cr2` `.cr3` `.nef` `.arw` `.dng` `.orf` `.rw2` `.pef`
  `.raf`, via `rawpy`/libraw) - demosaiced with the camera's as-shot white
  balance, standard sRGB-ish tone response (a normal starting point to edit
  further, not a scientific stretch like FITS).

`415 UNSUPPORTED_FORMAT` for anything else, an unreadable file, or a decoded
pixel count over the configured cap (`MAX_IMAGE_PIXELS` - a decompression-bomb
guard, independent of `max_image_size_mb`'s compressed-byte-size check).

The `/upload` response is `{ session_id, image_url, dimensions, file_size_bytes,
histogram, upload_timestamp, expires_at, is_stack }`. `is_stack` is `true` when
the upload opened as a composite session (linear stack data, above).

## Processing parameters

| Parameter | Min | Max | Default | Type |
|-----------|-----|-----|---------|------|
| contrast | 0.5 | 3.0 | 1.0 | float |
| exposure | -1.0 | 1.0 | 0.0 | float |
| saturation | 0.0 | 2.0 | 1.0 | float |
| highlights | -1.0 | 1.0 | 0.0 | float |
| shadows | -1.0 | 1.0 | 0.0 | float |
| whites | -1.0 | 1.0 | 0.0 | float |
| blacks | -1.0 | 1.0 | 0.0 | float |
| clarity | -1.0 | 1.0 | 0.0 | float |
| vibrance | 0.0 | 2.0 | 1.0 | float |
| denoise | 0 | 100 | 0 | int |
| denoise_engine | - | - | `"classic"` | `"classic"` \| `"deepsnr"` |
| chroma_denoise | 0 | 100 | 0 | int |
| vignette_correction | -100 | 100 | 0 | int (+brightens corners, -darkens) |
| gradient_reduction | 0 | 100 | 0 | int |
| dehaze | 0 | 100 | 0 | int |
| star_reduction | 0 | 100 | 0 | int |
| star_sensitivity | 0 | 100 | 50 | int |
| star_max_size | 0 | 100 | 30 | int |
| star_removal | 0 | 100 | 0 | int |
| star_recombine | 0 | 100 | 0 | int |
| star_removal_engine | - | - | `"classic"` | `"classic"` \| `"starnet2"` |
| sharpness | 0.0 | 2.0 | 1.0 | float |
| temperature | 2000 | 8000 | 6500 | int (Kelvin) |
| tint | -50 | 50 | 0 | int |
| curve_points | - | - | `[]` | array of `{x, y}` |
| red_curve_points | - | - | `[]` | array of `{x, y}` |
| green_curve_points | - | - | `[]` | array of `{x, y}` |
| blue_curve_points | - | - | `[]` | array of `{x, y}` |

`geometry` is a nested object applied **before** enhancement (rotate -> flip ->
straighten -> crop; crop coordinates are fractions of the rotated/flipped image):

| Field | Min | Max | Default | Type |
|-------|-----|-----|---------|------|
| straighten | -45 | 45 | 0 | float (degrees) |
| rotate_quarters | 0 | 3 | 0 | int (90 deg clockwise turns) |
| flip_horizontal | - | - | false | bool |
| flip_vertical | - | - | false | bool |
| crop_x / crop_y | 0.0 | 1.0 | 0.0 | float |
| crop_w / crop_h | >0 | 1.0 | 1.0 | float |

`crop_x + crop_w` and `crop_y + crop_h` must not exceed 1. A crop or a quarter
turn changes the result's dimensions.

`stack` is a nested object, used **only** for a composite session - one produced
by the stacker, or a linear upload (FITS / 16-bit, `is_stack: true`). It runs as
a non-destructive pre-stage on the 32-bit linear composite, ahead of every other
stage; it is ignored for an ordinary 8-bit image upload.

| Field | Min | Max | Default | Type |
|-------|-----|-----|---------|------|
| stretch | 0.0 | 1.0 | 0.5 | float (auto-stretch intensity: 0 subtle, 1 aggressive) |
| background_extraction | 0 | 100 | 100 | int (how much of the fitted sky gradient to remove) |
| color_calibration | - | - | true | bool (neutralise the sky, balance the channels) |

`curve_points` is a tone curve: a list of `{x, y}` 8-bit input/output level
pairs (both 0-255). `[]` (the default) means no curve. Otherwise: at least 2
points, the first at `x=0` and the last at `x=255`, and `x` strictly
increasing across the list - the backend interpolates a smooth curve between
them (see `docs/ALGORITHMS.md` "Tone curve"), so the frontend only needs to
send the points the user actually dragged, not a full 256-entry table:

```json
{ "curve_points": [{ "x": 0, "y": 0 }, { "x": 128, "y": 150 }, { "x": 255, "y": 255 }] }
```

`star_removal` (v0.3) turns star removal on: when it is above 0 the pipeline
splits after the background corrections - the stars are pulled out, every
creative stage runs on the starless image, and `star_recombine` screen-blends
the removed star flux back at the end (0 = fully starless output, 100 = stars at
full strength). Detection reuses `star_sensitivity` / `star_max_size`. `0` (the
default) is byte-identical to the flat pipeline. See `docs/ALGORITHMS.md`
"Star removal (starless)".

`star_removal_engine` / `denoise_engine` pick the backend for the split / the
`denoise` stage. `"classic"` (default) is the built-in code. `"starnet2"` /
`"deepsnr"` route through the operator-installed binary when one is configured and
working (see "External ML engines"), and silently fall back to `"classic"`
otherwise - so a client may always request them. With `"starnet2"`,
`star_sensitivity` / `star_max_size` have no effect; with `"deepsnr"`, denoise
runs early (before the tone stretch) and `chroma_denoise` still runs classically.

The canonical model is `app/models/processing.py`; keep this table in sync with it.

## WebSocket messages

`/ws/processing-status/{job_id}` and `/ws/stack-status/{job_id}` behave the same:
on connect the server sends the current job state from the DB (catch-up for late
subscribers), then, if the job is still running and `PROCESSING_MODE=queue`,
relays live events from Redis until a terminal status arrives, then closes.

```json
{
  "job_id": "job-abc123def456",
  "session_id": "550e8400-...",
  "status": "processing",
  "progress_percent": 45,
  "current_step": "denoise",
  "detail": null,
  "error": null,
  "timestamp": "2026-09-03T14:32:15Z"
}
```

`detail` is an optional short string for the current step - for stacking it is a
`"340/1066"` frame counter.

`status`: `queued`, `processing`, `completed`, `failed`, `superseded` (or
`unknown` if the `job_id` is not found). `superseded` means a newer `/process`
for the same session arrived while this job was still queued - it will not run
and its result should be ignored. Image steps: `geometry`, `color_correction`,
`vignette_correction`, `gradient_reduction`, `dehaze`, `contrast`, `exposure`,
`highlights_shadows`, `whites_blacks`, `tone_curve`, `channel_curves`,
`saturation`, `vibrance`, `clarity`, `denoise`, `chroma_denoise`,
`star_reduction`, `sharpness`, `rendering`, `done`. With `star_removal` set, the
extra steps `star_removal` (after `dehaze`) and `star_recombine` (last) bracket
the creative stages. For a stacked-composite session a `stack_base` step runs
first (the linear `stack` pre-stage). Stack steps: `calibration`,
`registration`, `normalization`, `integration`, `post-processing`, `done`.

In the default `PROCESSING_MODE=sync`, the job is already `completed` when
`/process` returns; the WebSocket just replays that final state.

`POST /process` / `POST /presets/{id}/apply/{sid}` return
`{ session_id, job_id, status, preview_url, estimated_time_seconds, ws_status_url }`.

## Presets

`GET /presets` returns `{ "presets": [...], "total": N }`. Each preset is
`{ preset_id, name, category, description, parameters, author, is_favorite }`
where `parameters` is a full `ProcessingParameters` object (missing fields filled
with their defaults).

Five built-ins are always present (`author: "system"`): **Nebula**, **Galaxy**,
**Deep Field**, **Lunar**, **Cluster**. They cannot be deleted (403).

`POST /presets` takes `{ name, parameters, description?, category? }` and returns
`201 { preset_id, name, created_at }`. Duplicate names give `400
DUPLICATE_RESOURCE`; more than 50 user presets gives `413 PAYLOAD_TOO_LARGE`.

`POST /presets/{preset_id}/apply/{session_id}` runs the pipeline with that
preset's parameters and returns the same body as `POST /process`.

`DELETE /presets/{preset_id}` returns `204`; deleting a built-in gives `403`.
The editor shows a delete affordance only on `author != "system"` presets.

## Depth shift

`POST /depth-shift/{session_id}` takes `{ intensity?, focus_point?, num_layers? }`
(`num_layers` 2-12, default 7) and returns:

```json
{
  "session_id": "...",
  "num_layers": 7,
  "depth_map_url": "/api/depth-shift/{id}/depth_map",
  "depth_layers": [
    { "layer_id": 0, "depth_range": [0.0, 0.143], "image_url": "/api/depth-shift/{id}/layer_0" }
  ],
  "statistics": { "min_depth": 0, "max_depth": 255, "mean_depth": 40,
                  "median_depth": 12, "bright_areas_percent": 6.2 }
}
```

Layers are ordered far (index 0, shifts most in the parallax) to near. Each
`/layer_{index}` is a BGRA PNG (transparent outside its depth band);
`/depth_map` is a grayscale PNG. `GET /depth-shift/{id}/metadata` reports
`depth_map_generated` and, once generated, the statistics and layer URLs.

`focus_point` (`{ x, y }`, both 0-1, image-space fractions) is optional and
**omitted by default** - not sent means "no focal point chosen", pure
gradient-based depth (detail reads as near), exactly as before this field did
anything. When sent, a radial field centred on that point is blended in, so
the chosen point reads as "near" too - see `docs/ALGORITHMS.md` "Focal point".
`(0.5, 0.5)` is a real, deliberately-picked center, not a default, so it's
distinguished from "omitted" by the field's *presence*, not its value.

## Star mask

`POST /star-mask/{session_id}` takes `{ sensitivity?, max_size? }` (both 0-100,
defaults 50 / 30, same semantics as the `star_sensitivity` / `star_max_size`
processing parameters) and returns:

```json
{
  "session_id": "...",
  "source_count": 42,
  "stars": [
    { "x": 0.42, "y": 0.13, "radius": 0.006 }
  ]
}
```

Detection runs against the session's full-resolution **original** image - the
same input the `star_reduction` pipeline stage analyses - so the reported
count matches what actually gets shrunk. (An earlier version ran this against
the downscaled preview image to stay fast; detection is now cheap enough
(~140ms even at 24MP) that there's no accuracy/speed trade-off left to make.)
`x` / `y` / `radius` are fractions (0-1) of the image's width / height /
longest side, so the frontend can position an overlay without needing the
image's pixel dimensions.

## Auto Astro

`POST /auto-astro/{session_id}` takes no body. It analyses the session's
original image (histogram black/white point, star density) and applies a
computed parameter set - a dynamic alternative to a fixed preset. Returns the
same shape as `POST /process/{session_id}` plus the computed `parameters`, so
the frontend can sync its sliders in one round trip:

```json
{
  "session_id": "...",
  "job_id": "job-...",
  "status": "completed",
  "preview_url": "/api/preview/{id}",
  "estimated_time_seconds": 0,
  "ws_status_url": "/ws/processing-status/job-...",
  "parameters": { "contrast": 1.8, "exposure": 0.1, "star_reduction": 35, "..." : "..." }
}
```

Scope is deliberately limited to what histogram/black-point/star-density can
drive with confidence: `contrast`, `exposure`, `highlights`, `shadows`, and
`star_reduction`. Everything else stays at its `ProcessingParameters` default.
See `docs/ALGORITHMS.md` "Auto Astro" for the heuristic.

## Client config

`GET /config` returns the non-sensitive runtime limits the web UI needs before a
session exists - the upload size cap it pre-checks against and shows, and the
stacking limits. No `ADMIN_ENABLED` gate (unlike `GET /admin/app-settings`,
which returns the full settings object):

```json
{
  "max_image_size_mb": 100,
  "stacking_enabled": true,
  "stacking_max_frames": 2000,
  "starless_engines": ["classic"],
  "denoise_engines": ["classic"]
}
```

Values track `app_settings.json` - change `max_image_size_mb` in Settings and
the upload screen's hint and pre-flight check follow.

`starless_engines` / `denoise_engines` list the processing engines the editor may
offer. `"classic"` is always present; `"starnet2"` / `"deepsnr"` appear only when
the operator has configured a working external binary (see "External ML engines"
below, `docs/DEPLOYMENT.md`, and `THIRD_PARTY.md`).

## External ML engines

Optional star removal (StarNet2) and denoise (DeepSNR) via an operator-installed
binary, invoked as a subprocess. **Nothing is bundled** - the operator downloads
the tool from `starnetastro.com`, mounts it into the API and worker containers,
and sets `starnet2_path` / `deepsnr_path` (and optional `starnet2_stride` /
`deepsnr_stride`) in Settings. Empty paths (the default) leave the classical
engines as the only option; a configured, working engine then appears in
`starless_engines` / `denoise_engines` and as a per-edit picker in the editor.

`GET /admin/engine-status` (gated by `ADMIN_ENABLED`) probes the configured paths
with `<binary> --version` and drives the status line in Settings:

```json
{
  "starnet2": {
    "configured": true,
    "found": true,
    "version": "2.6.1",
    "known_good": true,
    "detail": "StarNet2 2.6.1 detected"
  },
  "deepsnr": {
    "configured": false,
    "found": false,
    "version": null,
    "known_good": false,
    "detail": "No path configured"
  }
}
```

`known_good` is false when the binary's version falls outside the range this
release was tested against - the engine still runs, with a warning in Settings.
The probe result is memoised until the next settings change.

## Update check

`GET /version` reads the running version directly (no caching needed - it's a
constant for the life of the process). `GET /version/check-updates` reports
whether a newer GitHub release exists:

```json
{
  "current_version": "0.1.0",
  "latest_version": "0.2.0",
  "update_available": true,
  "release_url": "https://github.com/myastroboard/myastroshine/releases/tag/v0.2.0",
  "release_name": "v0.2.0",
  "release_notes": "### Added\n- ...",
  "published_at": "2026-09-05T00:00:00Z",
  "error": null
}
```

Backed by `VersionCheckService` (`app/services/version_check.py`): queries
`GET https://api.github.com/repos/myastroboard/myastroshine/releases/latest`
and caches the result in memory for 4 hours, so polling this endpoint never
translates into hammering GitHub's (unauthenticated, 60 req/hour) rate limit.
Every failure path (timeout, 404, GitHub's own rate limit, a malformed
response, ...) is caught and returned as a normal 200 with a non-null `error`
and `update_available: false` - this endpoint never 5xxs on a GitHub outage.
The frontend (`useVersionCheck.ts`) polls this every 4h and re-verifies
`update_available` itself before showing the discreet update banner
(`UpdateBanner.tsx`), so a stale or incorrect cache can never present as a
downgrade.

## Webhook tokens

A webhook token pairs the AstroDex integration with this instance. Create one
from the Settings UI or `POST /tokens { name, expires_in_days? }` -> `201`:

```json
{
  "id": "...", "name": "AstroDex prod", "token_prefix": "mas_1wZcTkdO",
  "created_at": "...", "expires_at": null, "revoked": false,
  "token": "mas_<long secret>",        // the value; its first 12 chars are the kid
  "signing_secret": "<64 hex chars>"   // HMAC key, both directions
}
```

`token` and `signing_secret` are shown **only** in this response. `GET /tokens`
never returns them. `DELETE /tokens/{id}` revokes immediately. Paste both into
MyAstroBoard's MyAstroShine connector; it mints the handoff tokens below.

## AstroDex integration

The browser is opened here from MyAstroBoard with a signed **handoff token** in
the URL. This instance never needs to be reachable *from* the board - it only
ever calls out - so the flow works whether the board is on the LAN or behind a
public reverse proxy. Full design:
`initial_plan/PASSATION_MYASTROBOARD_INTEGRATION.md`.

**Handoff token** - `b64url(payload).b64url(HMAC_SHA256(b64url(payload), secret))`,
b64url without padding, the signature segment is the raw digest (not hex). The
payload claims: `kid` (first 12 chars of the webhook token), `callback_base`
(the board origin, set by the board), `item_id`, `picture_id`, `user_id`, `iat`,
`exp` (12 h), `jti` (single-use, enforced by the board on return).

**`POST /astrodex/handoff/resume`** `{ handoff }` -> verify the signature and
expiry, check `callback_base` against the `astrodex_callback_urls` allowlist,
`GET {callback_base}/api/astrodex/integration/source` (+ `/source/image`) for the
picture and its metadata, open a session. Returns
`200 { session_id, image_url, dimensions, histogram, object_name, astrodex_item_id }`.

**`POST /astrodex/handoff/return`** `{ session_id }` -> encode the processed
image, POST it back as `multipart/form-data` to
`{callback_base}/api/astrodex/integration/enhanced` with fields `handoff`,
`payload` (`canonical_json({ parameters, myastroshine_version })`), and `image`.
Signed with `X-Webhook-Signature: sha256=<hex>` over
`canonical_json(payload) + "\n" + sha256_hex(image_bytes)`, keyed by the webhook
token's `signing_secret`. The board files the result as a **new** picture on the
same object (the original is never replaced). Retries `astrodex_max_retries`
times with backoff; a `409` means the board already has it. Returns
`200 { session_id, status, astrodex_item_id }`; a delivery failure is `502`.

`callback_base` must match `astrodex_callback_urls` when that allowlist is set
(empty = every URL refused - the main SSRF guard).

## Stacking

Frames are ingested as linear `float32` (FITS CFA mosaics kept intact, camera RAW
demosaiced linearly, 8-bit previews sRGB-linearised). The pipeline calibrates
each frame (master dark/flat/bias when uploaded), scores every sub and
auto-rejects the worst, registers by asterism matching, normalises to the
reference, and combines with sigma rejection and weighting, all in bounded
memory. Full detail: [ALGORITHMS.md](ALGORITHMS.md#stacking).

1. `POST /stack/initiate` `{ frame_count, registration_transform?, combination_method?,
   rejection_algo?, weighting?, cosmetic_correction?, quality_filter?, post_process?,
   drizzle_factor? }`
   -> `202 { stack_id, status: "waiting_for_frames", frame_count, received_frames }`.
   - `registration_transform`: `translation` / `similarity` (default) / `affine`
   - `combination_method`: `average` (default) / `median`
   - `rejection_algo`: `none` / `sigma` / `winsorized_sigma` (default)
   - `weighting`: `none` / `noise` (default) / `quality` (the frame-quality score)
   - `cosmetic_correction`: bool (default `true`) - replace hot/dead pixels
     (from the master dark/flat) with a neighbour median
   - `quality_filter`: `off` / `lenient` / `moderate` (default) / `strict` -
     auto-reject strength for the per-frame quality scorer
   - `post_process`: bool (default `true`) - crop the field-rotation wedge of
     the composite before it opens in the editor (the stretch / background /
     colour steps moved into the editor's non-destructive "Stack" step)
   - `drizzle_factor`: `1` (default, off) / `2` / `3` - variable-pixel
     reconstruction onto a finer grid, an extra pass after the normal stack.
     Slower, correlates neighbouring-pixel noise; for a large, well-dithered set
2. `POST /stack/{stack_id}/upload-frame` (multipart: `frame_index`, `file`) ->
   `202 { frame_index, received_frames, frame_count, status }`. `status` becomes
   `"ready"` once every frame is in.
3. `POST /stack/{stack_id}/upload-frames` (multipart: `start_index`, `files` =
   many files) -> `202 { stack_id, status, frame_count, received_frames }`. The
   frontend sends frames in batches of a few dozen so a thousand-frame session is
   tens of requests, not a thousand.
4. `POST /stack/{stack_id}/upload-archive` (multipart: `file` = a `.zip`) ->
   the same response. Image members are ingested in filename order and assigned
   indices from `received_frames` upward, up to `frame_count`.
5. `POST /stack/{stack_id}/frame/{index}/exclude` `{ excluded: bool }` ->
   `200 { index, thumb_url, excluded, quality }`. Toggles a frame in or out of
   the stack. `excluded: false` also **rescues** the frame from the quality
   auto-reject on the next run; `excluded: true` drops that protection.
6. `GET /stack/{stack_id}/frame/{index}/thumb` -> a ~256 px auto-stretched JPEG
   for the frame grid. Not rate-limited.
7. `POST /stack/{stack_id}/calibration/{kind}/frames` (multipart: `files` = many
   files), `kind` = `dark` / `flat` / `bias` / `dark_flat` -> `202
   { frames: { dark, flat, bias, dark_flat }, cosmetic_correction }`. Appends
   calibration subs; masters (per-pixel median) are built and cached at `process`,
   and rebuilt when more subs arrive.
8. `DELETE /stack/{stack_id}/calibration/{kind}` -> the same body. Drops every
   sub of that kind and any master derived from it.
9. `POST /stack/{stack_id}/process` -> `200`. In `PROCESSING_MODE=sync` the
   pipeline runs in the request and the response is already `completed`; in
   `queue` it returns `processing` with a `job_id` / `ws_status_url` and the
   worker runs it (follow `/ws/stack-status/{job_id}`). An optional body
   `{ registration_transform?, combination_method?, rejection_algo?, weighting?,
   cosmetic_correction?, quality_filter?, post_process?, drizzle_factor? }`
   re-stacks with a changed setting - no re-upload, each run makes a fresh
   composite session. Changing only the combination / rejection / weighting /
   drizzle resumes from the aligned frames of the previous run (within ~30 min):

```json
{
  "stack_id": "...",
  "status": "completed",
  "job_id": "job-...",
  "ws_status_url": "/ws/stack-status/job-...",
  "session_id": "<composite session>",
  "stacked_image_url": "/api/preview/<session_id>?full=true",
  "statistics": {
    "frames_stacked": 46, "frames_excluded": 4, "frames_auto_rejected": 2,
    "combination_method": "average", "registration_transform": "similarity",
    "snr_improvement": 6.78, "measured_noise_reduction": 5.1, "calibrated": true,
    "post_processed": true
  },
  "frames": [{ "index": 0, "thumb_url": "/api/stack/.../frame/0/thumb", "excluded": false,
    "quality": { "star_count": 1180, "fwhm": 2.8, "roundness": 0.86, "background": 0.008,
      "snr": 74.0, "score": 88.0, "weight": 1.05, "accepted": true, "reject_reason": null } }],
  "calibration": { "frames": { "dark": 20, "flat": 15, "bias": 0, "dark_flat": 0 },
    "cosmetic_correction": true }
}
```

An auto-rejected frame comes back with `excluded: true` and
`quality.accepted: false` (`reject_reason` one of `clouds` / `soft` / `trailed`
/ `bright_sky`); `quality` is `null` until the stack has been run once.

The composite is a normal session: enhance it with `POST /process`, fetch it with
`GET /preview`, download it with `POST /download`. `GET /stack/{stack_id}` returns
the same body at any time, always with the current `frames` list (`error` is set
when `status` is `"failed"`). See docs/ALGORITHMS.md for the pipeline.
