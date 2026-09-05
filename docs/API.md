# MyAstroShine API

Base URL: `http://localhost:8002/api` (configurable via `VITE_API_URL` on the
frontend). Most routes are unauthenticated (local deployment). The AstroDex
routes (`/astrodex/receive`, `/send-to-astrodex`) require a long-lived webhook
token: `Authorization: Bearer <token>`, created and revoked from the Settings UI
(`/api/tokens`).

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
`/star-mask/{id}`, and `/stack/*`:

- **Requests per minute** (`rate_limit_per_minute`, default **120**, not the
  API spec's original 10 - the editor re-processes on every slider change,
  500ms debounced, so a normal editing session alone can approach 120/min):
  a fixed 60-second window, shared across all of the routes above (not
  per-route).
- **Concurrent processing jobs** (`max_concurrent_jobs_per_ip`, default 5):
  checked against non-terminal rows in the `jobs` table, so it holds under
  both `PROCESSING_MODE=sync` and `queue`.

Both settings, plus a `rate_limit_enabled` switch, are editable from
**Settings -> Advanced** (`app_settings.json`, see docs/DEPLOYMENT.md) - no
restart needed. Over either limit returns `429` with `error_code:
"RATE_LIMITED"`.

## Status

Every route is implemented and tested end to end: health,
upload/preview/process/download, presets, depth-shift, webhook tokens, AstroDex
integration (signed background webhook + retry), the full stacking pipeline, the
Celery job queue (`PROCESSING_MODE=queue`), and the progress WebSockets.

## Endpoints

| Method | Path | Purpose | Sprint |
|--------|------|---------|--------|
| GET | `/health` | System health | 1 |
| GET | `/admin/app-settings` | Current runtime settings (`app_settings.json`) | 1 |
| POST | `/admin/app-settings` | Replace runtime settings (gated by `ADMIN_ENABLED`) | 1 |
| GET | `/admin/logs` | Tail the log file, newest first (`limit`, `offset`, `level`) | 1 |
| GET / POST | `/admin/logs/level` | Read / change the file and console log levels | 1 |
| POST | `/admin/logs/clear` | Empty `myastroshine.log` | 1 |
| GET | `/admin/logs/export` | ZIP of the logs (main + rotations + worker) | 1 |
| POST | `/upload` | Upload an image, open a session | 1 |
| GET | `/preview/{session_id}` | Session image: `?full=true` full-res result, `?original=true` untouched upload (add `&geometry=true` to apply the session's current crop/rotate/flip/straighten, no colour/tone enhancement - keeps the before/after comparison aligned once geometry has changed the result's frame), default downscaled result | 1 |
| POST | `/process/{session_id}` | Apply enhancement parameters | 1 / 3 |
| WS | `/ws/processing-status/{job_id}` | Real-time job progress | 3 |
| POST | `/download/{session_id}` | Download the processed image | 2 |
| POST | `/depth-shift/{session_id}` | Generate depth map + parallax layers | 4 |
| GET | `/depth-shift/{session_id}/metadata` | Depth statistics + layer URLs | 4 |
| GET | `/depth-shift/{session_id}/depth_map` | Depth map as a grayscale PNG | 4 |
| GET | `/depth-shift/{session_id}/layer_{index}` | Single BGRA layer PNG | 4 |
| POST | `/star-mask/{session_id}` | Detect stars in the preview image for a mask overlay | v0.2 |
| GET | `/tokens` | List webhook tokens (metadata only) | 4 |
| POST | `/tokens` | Create a webhook token (raw value shown once) | 4 |
| DELETE | `/tokens/{token_id}` | Revoke a token | 4 |
| POST | `/astrodex/receive` | Receive an image pushed from AstroDex (bearer auth) | 4 |
| POST | `/send-to-astrodex` | Send the enhanced image back (bearer auth, signed webhook) | 4 |
| GET | `/presets` | List presets (5 built-ins + user presets) | 3 |
| POST | `/presets` | Save a user preset | 3 |
| DELETE | `/presets/{preset_id}` | Delete a user preset (403 for built-ins) | 3 |
| POST | `/presets/{preset_id}/apply/{session_id}` | Apply a preset | 3 |
| POST | `/stack/initiate` | Open a stacking session | 6 |
| POST | `/stack/{stack_id}/upload-frame` | Upload one frame | 6 |
| POST | `/stack/{stack_id}/process` | Align + combine frames | 7 |
| GET | `/stack/{stack_id}` | Stack result and statistics | 7 |
| WS | `/ws/stack-status/{job_id}` | Real-time stacking progress | 6 |

## Processing parameters

| Parameter | Min | Max | Default | Type |
|-----------|-----|-----|---------|------|
| contrast | 0.5 | 3.0 | 1.0 | float |
| brightness | -1.0 | 1.0 | 0.0 | float |
| saturation | 0.0 | 2.0 | 1.0 | float |
| highlights | -1.0 | 1.0 | 0.0 | float |
| shadows | -1.0 | 1.0 | 0.0 | float |
| clarity | -1.0 | 1.0 | 0.0 | float |
| vibrance | 0.0 | 2.0 | 1.0 | float |
| denoise | 0 | 100 | 0 | int |
| star_reduction | 0 | 100 | 0 | int |
| star_sensitivity | 0 | 100 | 50 | int |
| star_max_size | 0 | 100 | 30 | int |
| sharpness | 0.0 | 2.0 | 1.0 | float |
| temperature | 2000 | 8000 | 6500 | int (Kelvin) |
| tint | -50 | 50 | 0 | int |
| depth_shift_intensity | -100 | 100 | 0 | int |

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
  "error": null,
  "timestamp": "2026-09-03T14:32:15Z"
}
```

`status`: `queued`, `processing`, `completed`, `failed` (or `unknown` if the
`job_id` is not found). Image steps: `geometry`, `color_correction`, `contrast`,
`brightness`, `highlights_shadows`, `saturation`, `vibrance`, `clarity`,
`denoise`, `star_reduction`, `sharpness`, `rendering`, `done`. Stack steps:
`registration`, `background_normalization`, `cosmic_ray_rejection`,
`combination`, `done`.

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

Detection runs against the session's cached **preview** image (not the
full-resolution result), so the mask stays fast enough to recompute on every
slider change while the frontend's mask overlay is on - it's a preview aid, not
the exact set of stars the full-resolution `star_reduction` stage will shrink,
though both share the same detector. `x` / `y` / `radius` are fractions (0-1)
of the preview image's width / height / longest side, so the frontend can
position an overlay without needing the image's pixel dimensions.

## Webhook tokens

Long-lived bearer tokens authenticate AstroDex to this instance. Create from the
Settings UI or `POST /tokens { name, expires_in_days? }` -> `201`:

```json
{
  "id": "...", "name": "AstroDex prod", "token_prefix": "mas_1wZcTkdO",
  "created_at": "...", "expires_at": null, "revoked": false,
  "token": "mas_<long secret>",        // bearer credential
  "signing_secret": "<64 hex chars>"   // configure in AstroDex to verify webhooks
}
```

`token` and `signing_secret` are shown **only** in this response. `GET /tokens`
never returns them. `DELETE /tokens/{id}` revokes immediately (`401` on next use).

## AstroDex integration

**Inbound** - `POST /astrodex/receive` (multipart: `image_id`, `image`,
`callback_url`, `callback_token?`; `Authorization: Bearer <token>`) opens a
session and records the callback. Returns `201 { session_id, image_url, ... }`.

**Outbound** - `POST /send-to-astrodex` (`{ session_id, astrodex_image_id,
astrodex_callback_url }`; bearer auth) returns `202` immediately and delivers
this signed payload in the background:

```json
{
  "event": "image_enhanced",
  "source": "MyAstroShine",
  "timestamp": "2026-09-03T14:32:20Z",
  "data": {
    "original_image_id": "astrodex_img_12345",
    "enhanced_image": { "blob": "<base64>", "format": "jpeg", "width": 3840,
                        "height": 2160, "file_size_bytes": 5242880 },
    "processing_metadata": { "session_id": "...", "parameters": { } },
    "preview_url": "/api/preview/...?full=true"
  }
}
```

Headers: `X-Webhook-Signature: sha256=<hmac>`,
`X-Webhook-Signature-Algorithm: HMAC-SHA256`. The HMAC is over
`canonical_json(payload)` (sorted keys, `(",", ":")` separators) keyed by the
token's `signing_secret` (or `ASTRODEX_WEBHOOK_SECRET` as fallback). Delivery
retries `ASTRODEX_MAX_RETRIES` times with exponential backoff; the
`astrodex_links` row tracks `webhook_status` (`pending` / `sent` / `failed`).
`astrodex_callback_url` must match `ASTRODEX_CALLBACK_URLS` when that allowlist
is set (else `403`).

## Stacking (v1.1)

1. `POST /stack/initiate` `{ frame_count, registration_method?, combination_method?,
   cosmic_ray_rejection?, background_normalization? }` -> `202 { stack_id, status:
   "waiting_for_frames", frame_count, received_frames }`.
2. `POST /stack/{stack_id}/upload-frame` (multipart: `frame_index`, `file`) ->
   `202 { frame_index, received_frames, frame_count, status }`. `status` becomes
   `"ready"` once every frame is in.
3. `POST /stack/{stack_id}/process` runs the pipeline synchronously and returns
   `200`:

```json
{
  "stack_id": "...",
  "status": "completed",
  "session_id": "<composite session>",
  "stacked_image_url": "/api/preview/<session_id>?full=true",
  "statistics": {
    "frames_stacked": 15, "frames_rejected": 0, "combination_method": "median",
    "cosmic_rays_removed": 42, "registration_success_rate": 100.0,
    "snr_improvement": 3.87
  }
}
```

The composite is a normal session: enhance it with `POST /process`, fetch it with
`GET /preview`, download it with `POST /download`. `GET /stack/{stack_id}` returns
the same body at any time (`error` is set when `status` is `"failed"`).
`registration_method` is `sift` / `orb`; `combination_method` is `median` / `mean`
/ `sigma_clip`. See docs/ALGORITHMS.md for the pipeline.
