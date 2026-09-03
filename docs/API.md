# MyAstroShine API

Base URL: `http://localhost:8002/api` (configurable via `VITE_API_URL` on the
frontend). No authentication in v1 (local deployment); token-based auth is planned
for v1.5+.

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

Common codes: `INVALID_PARAMETER` (400), `UNSUPPORTED_FORMAT` (415),
`SESSION_NOT_FOUND` (404), `SESSION_EXPIRED` (410), `PROCESSING_FAILED` (500),
`ASTRODEX_UNREACHABLE` (503).

## Status

Implemented and tested end to end: `GET /health`, `POST /upload`,
`GET /preview/{id}`, `POST /process/{id}` (synchronous), `POST /download/{id}`.
Everything below marked Sprint 3+ still answers `501 Not Implemented`.

## Endpoints

| Method | Path | Purpose | Sprint |
|--------|------|---------|--------|
| GET | `/health` | System health | 1 |
| POST | `/upload` | Upload an image, open a session | 1 |
| GET | `/preview/{session_id}` | Current preview JPEG (`?full=true` for full res) | 1 |
| POST | `/process/{session_id}` | Apply enhancement parameters | 1 / 3 |
| WS | `/ws/processing-status/{job_id}` | Real-time job progress | 3 |
| POST | `/download/{session_id}` | Download the processed image | 2 |
| POST | `/depth-shift/{session_id}` | Generate depth map + parallax layers | 4 |
| GET | `/depth-shift/{session_id}/metadata` | Depth statistics + layer URLs | 4 |
| GET | `/depth-shift/{session_id}/layer_{index}` | Single layer PNG (alpha) | 4 |
| POST | `/astrodex/receive` | Receive an image pushed from AstroDex | 4 |
| POST | `/send-to-astrodex` | Send the enhanced image back (signed webhook) | 4 |
| GET | `/presets` | List presets | 3 |
| POST | `/presets` | Save a preset | 3 |
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
| sharpness | 0.0 | 2.0 | 1.0 | float |
| temperature | 2000 | 8000 | 6500 | int (Kelvin) |
| tint | -50 | 50 | 0 | int |
| depth_shift_intensity | -100 | 100 | 0 | int |

The canonical model is `app/models/processing.py`; keep this table in sync with it.

## WebSocket messages

`/ws/processing-status/{job_id}` emits:

```json
{
  "job_id": "job_abc123",
  "status": "processing",
  "progress_percent": 45,
  "current_step": "denoise",
  "message": "Denoising in progress...",
  "timestamp": "2026-09-03T14:32:15Z"
}
```

Status values: `queued`, `processing`, `completed`, `failed`.
Step values: `stretching`, `contrast`, `highlights_shadows`, `clarity`, `denoise`,
`sharpness`, `color_correction`, `depth_estimation`, `rendering`.

## AstroDex webhook

`POST /send-to-astrodex` queues a signed `POST` to the AstroDex callback URL:

```json
{
  "event": "image_enhanced",
  "source": "MyAstroShine",
  "timestamp": "2026-09-03T14:32:20Z",
  "data": {
    "original_image_id": "astrodex_img_12345",
    "enhanced_image": { "blob": "<base64>", "format": "jpeg", "width": 3840, "height": 2160 },
    "processing_metadata": { "session_id": "...", "parameters": { } },
    "preview_url": "http://myastroshine.local/api/preview/..."
  },
  "signature": "sha256=...",
  "signature_algorithm": "HMAC-SHA256"
}
```

The signature is `HMAC-SHA256(secret, canonical_json(payload))` where canonical
JSON uses sorted keys and `(',', ':')` separators. The shared secret is
`ASTRODEX_WEBHOOK_SECRET`. Delivery retries with exponential backoff
(5s, 10s, 20s) before the webhook is stored as failed.
