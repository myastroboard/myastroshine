# 🔭 MyAstroShine

**A self-hosted astronomical image processing tool - enhancement, multi-image stacking, and depth effects.**

MyAstroShine automatically enhances astrophotography images, aligns and stacks 2-2000 frames to raise signal-to-noise, and adds a parallax "Depth Shift" effect - all from one Docker image, no account or cloud upload required. It integrates optionally with [MyAstroBoard](https://github.com/myastroboard/myastroboard)'s AstroDex but also runs entirely standalone.

---

## ✨ Features

- **Automatic enhancement** - contrast, clarity, noise reduction, dynamic stretching, dehaze, gradient and vignette correction, in a workflow-ordered editor with inline help
- **One-click Auto Astro** - analyses the image and applies an adaptive starting point; plus five built-in presets and your own
- **Tone + colour curves** - an interactive master RGB curve and independent red / green / blue curves
- **Star handling** - shrink stars in place, or lift them out entirely (starless workflow) and blend them back at the end
- **Geometry tools** - rotate, flip, straighten, and crop before the pixel pipeline runs
- **Depth Shift** - a parallax effect that adds a sense of 3D depth to a single frame
- **Stacking** - align and combine 2-2000 linear frames (calibration, per-frame quality scoring, asterism-matching registration, sigma-clip combination, optional drizzle) to raise SNR
- **Optional ML engines** - point it at an operator-installed StarNet2 / DeepSNR binary (nothing bundled)
- **FITS / camera RAW / 16-bit** upload support, plus edit milestones and a folder-watch stacking mode
- **English + French** UI, light / dark themes
- **AstroDex integration** - capture in AstroDex, enhance here, send back via a signed webhook
- **Standalone workflow** - manual upload, edit, download - no other MyAstroBoard component required

---

## 🚀 Quick Start

```bash
docker pull myastroboard/myastroshine:latest
```

Simplest run (in-request processing, no queue):

```bash
docker run -d -p 8002:8002 -e APP_ENV=production \
  -v myastroshine_data:/data myastroboard/myastroshine:latest
```

Full setup with Docker Compose (adds a Celery worker + Redis for queued
processing and background session cleanup):

```yaml
services:
  api:
    image: myastroboard/myastroshine:latest
    ports:
      - "8002:8002"
    environment:
      - APP_ENV=production
      - PROCESSING_MODE=queue
      - REDIS_URL=redis://redis:6379/0
      - CELERY_BROKER_URL=redis://redis:6379/1
    volumes:
      - myastroshine_data:/data
    depends_on: [redis]
    restart: unless-stopped
  worker:
    image: myastroboard/myastroshine:latest
    command: celery -A app.tasks.celery_app worker -B --loglevel=info
    environment:
      - APP_ENV=production
      - PROCESSING_MODE=queue
      - REDIS_URL=redis://redis:6379/0
      - CELERY_BROKER_URL=redis://redis:6379/1
    volumes:
      - myastroshine_data:/data
    depends_on: [redis]
    restart: unless-stopped
  redis:
    image: redis:7-alpine
    restart: unless-stopped
volumes:
  myastroshine_data:
```

The full `docker-compose.yml` (with healthchecks and comments) is in the
[repository](https://github.com/myastroboard/myastroshine/blob/main/docker-compose.yml).
No `.env` editing required - everything tunable (CORS, upload limits,
stacking defaults, log levels, ...) is edited from **Settings** in the UI and
persisted under the data volume. See the
[Deployment Guide](https://github.com/myastroboard/myastroshine/blob/main/docs/DEPLOYMENT.md).

---

## 🐳 Available Tags

| Tag | Description |
|-----|-------------|
| `latest` | Latest stable release |
| `x.y.z` | Specific version (e.g. `0.2.0`) |
| `x.y` | Latest patch of a minor version |
| `x` | Latest minor of a major version |

---

## 🖥️ Supported Platforms

| Platform | Architecture |
|----------|-------------|
| `linux/amd64` | x86_64 - PC, server, most NAS (Synology Intel/AMD) |
| `linux/arm64` | ARM 64-bit - Raspberry Pi 4/5, Apple Silicon |

---

## 📋 Requirements

- Docker (Compose recommended for the queued-processing setup)
- Linux host or compatible Docker environment

---

## 📚 Documentation

- [Documentation index](https://github.com/myastroboard/myastroshine/blob/main/docs/README.md)
- [Features](https://github.com/myastroboard/myastroshine/blob/main/docs/FEATURES.md)
- [Deployment Guide](https://github.com/myastroboard/myastroshine/blob/main/docs/DEPLOYMENT.md)
- [Troubleshooting](https://github.com/myastroboard/myastroshine/blob/main/docs/TROUBLESHOOTING.md)
- [API Reference](https://github.com/myastroboard/myastroshine/blob/main/docs/API.md)
- [Contributing](https://github.com/myastroboard/myastroshine/blob/main/CONTRIBUTING.md)
- [Security Policy](https://github.com/myastroboard/myastroshine/blob/main/SECURITY.md)

---

## 🐛 Support

Issues and feature requests: [GitHub Issues](https://github.com/myastroboard/myastroshine/issues)

## 📄 License

Licensed under [AGPL-3.0-or-later](https://github.com/myastroboard/myastroshine/blob/main/LICENSE).
Source code available at: [github.com/myastroboard/myastroshine](https://github.com/myastroboard/myastroshine)
