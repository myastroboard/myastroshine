# Features

What MyAstroShine does, from a user's point of view. The [API](API.md) documents
the contract; the [algorithms](ALGORITHMS.md) documents the maths. This page is
the tour.

## Contents

- [Two modes](#two-modes)
- [Uploading](#uploading)
- [The single-image editor](#the-single-image-editor)
  - [Start: Auto Astro and presets](#start-auto-astro-and-presets)
  - [1. Framing](#1-framing)
  - [2. Background](#2-background)
  - [3. Light](#3-light)
  - [4. Curves](#4-curves)
  - [5. Colour](#5-colour)
  - [6. Detail](#6-detail)
  - [7. Stars](#7-stars)
  - [8. Depth](#8-depth)
  - [Export](#export)
- [Edit milestones](#edit-milestones)
- [Stacking](#stacking)
  - [The Stack step](#the-stack-step)
  - [Calibration frames](#calibration-frames)
  - [Folder-watch ingest](#folder-watch-ingest)
- [External ML engines](#external-ml-engines)
- [Presets](#presets)
- [AstroDex integration](#astrodex-integration)
- [Themes and language](#themes-and-language)
- [Settings](#settings)

## Two modes

A toggle at the top of the app switches between:

- **Single image** - upload one frame (or a stacked composite from elsewhere),
  edit it with the workflow below, download or hand it back to AstroDex.
- **Stacking** - upload many sub-exposures, review and calibrate them, combine
  them into one high-SNR composite, then edit that composite in the single-image
  editor.

## Uploading

`Upload` accepts:

| Kind | Handling |
|------|----------|
| 8-bit JPEG / PNG / TIFF | used as-is |
| 16-bit PNG / TIFF (a stacked frame from Siril / DSS / PixInsight) | auto-stretched (screen-transfer-function), not bit-shifted |
| FITS (`.fits` / `.fit` / `.fts`) | linear science data, always auto-stretched; 2D read as mono, 3-plane as RGB |
| Camera RAW (`.cr2` `.cr3` `.nef` `.arw` `.dng` `.orf` `.rw2` `.pef` `.raf`) | demosaiced with the camera's as-shot white balance |

The size cap (`max_image_size_mb`, default 100) and a decoded-pixel-count cap are
both enforced. Anything else is rejected with `415 UNSUPPORTED_FORMAT`.

## The single-image editor

Three panes: a numbered **workflow rail** on the left, the active step's
**inspector** in the middle, and a **pinned preview + histogram** on the right.
The steps run in the same order as the backend pipeline, so working top to bottom
gives predictable results. Each step shows a dot on the rail once its values
leave the default. Every change re-renders the preview automatically (debounced).

### Start: Auto Astro and presets

**Auto Astro** analyses the image (histogram black/white point, star density) and
applies a computed starting point - a contrast/exposure stretch that separates
the object from the background, plus a gentle log-scaled star reduction. It is a
starting point, not a finished edit.

**Presets** apply a saved look in one click. Auto Astro and presets both keep
your current framing - a look is not a composition.

### 1. Framing

Crop, level the horizon (straighten, -45 to +45 deg), rotate in quarter turns,
and flip. Edited directly on the preview. Everything after this works on the
framed image. (Not available for a stacked composite - its dimensions aren't
carried through.)

### 2. Background

Corrections to the raw signal, before any creative grading:

- **White balance** - temperature (2000-8000 K) and tint.
- **Vignette correction** - lifts the corners against lens falloff (a generic
  radial model, not a per-lens profile).
- **Gradient reduction** - flattens smooth light-pollution / sky-glow gradients.
- **Dehaze** - dark-channel-prior haze removal for contrast lost to a veiling
  glow.

### 3. Light

Overall tone: **exposure**, **contrast**, **highlights**, **shadows**, and the
narrower, more aggressive **whites** / **blacks** clipping-point controls.

### 4. Curves

An interactive curve graph - drag points to reshape, double-click to add or
remove one. A **master RGB** curve plus independent **red / green / blue** curves
for grading or a colour cast a single white-balance gain can't reach. Points make
a smooth monotone spline, never a faceted polyline, and never overshoot into
crushed shadows or blown highlights.

### 5. Colour

**Saturation** scales all colour; **vibrance** boosts the muted colours while
protecting the already-saturated ones.

### 6. Detail

Local texture, once tone and colour are settled: **clarity** (micro-contrast),
**denoise** (luma), **colour noise reduction** (Cr/Cb only - colour speckle
tolerates far more smoothing than brightness detail), and **sharpness**.

### 7. Stars

Two independent tools, sharing one detector (`star sensitivity` / `star max
size`, previewable as a live "N sources detected" overlay):

- **Reduce** - shrink detected stars in place. Each star erodes toward its own
  local background, so it can't crush to a black dot or bloat into a flat disc.
- **Remove (starless)** - split the stars out right after the background
  corrections; every creative stage then works on the nebula alone, and **bring
  stars back** screen-blends them in at the end (0 = fully starless, 100 = full
  strength). The classical reconstruction handles a nebula or galaxy over a
  normal star field well; a dense Milky Way field is its known ceiling - that is
  what the StarNet2 engine is for.

### 8. Depth

**Depth Shift** adds a parallax sense of 3D to a single frame. Pick a focal point
on the preview (click), then open the viewer for an interactive parallax preview.
Depth is estimated from image detail (stars and structure read as near, smooth
sky as far); the focal point pulls the chosen spot forward too.

### Export

Download the result (JPEG), **Send back to AstroDex** (when the session was
opened from AstroDex), or **Save as preset** to reuse the current settings later.

## Edit milestones

A timeline under the preview. Save the current state (sliders, curves, framing,
and the Depth Shift focal point) as a checkpoint and click back to it if an edit
goes too far. The first milestone is the unedited original.

## Stacking

A four-step workflow mirroring the editor: **Frames -> Calibration -> Settings
-> Result**.

1. **Frames** - drop 2 to `stacking_max_frames` (default 2000) sub-exposures.
   They upload in batches; a `.zip` works too. Review the thumbnail grid and
   exclude a trailed or clouded sub. Every frame is scored (star count, FWHM,
   roundness, background, SNR) and the worst are auto-rejected - unchecking a
   frame rescues it from that.
2. **Calibration** - optionally add dark / flat / bias / dark-flat subs (see
   below).
3. **Settings** - registration transform (`translation` / `similarity` /
   `affine`), combination (`average` / `median`), pixel rejection (`none` /
   `sigma` / `winsorized_sigma`), per-frame weighting (`none` / `noise` /
   `quality`), quality-filter strength, cosmetic correction, and drizzle
   (`1` off / `2` / `3`).
4. **Result** - registration RMS, frames stacked / excluded / auto-rejected,
   SNR improvement, measured noise reduction. **Enhance composite** hands it to
   the single-image editor.

The pipeline works in linear `float32` throughout: calibrate each frame on the
CFA mosaic, score and reject, register by asterism (triangle) matching,
normalise to the reference, and combine with sigma rejection and weighting - all
in bounded memory, so a thousand-frame night fits. Re-stacking with only the
combination / rejection / weighting / drizzle changed resumes from the aligned
frames.

### The Stack step

A stacked composite opens in the editor with an extra **Stack** step at the top -
a non-destructive pre-stage on the 32-bit linear data:

- **Stretch** (0-1) - auto-stretch intensity; higher lifts fainter signal at the
  cost of a brighter, noisier background.
- **Background extraction** (0-100) - fits and subtracts the sky gradient
  (degree-2 polynomial, so it can never be mistaken for a nebula).
- **Colour calibration** (on/off) - neutralises the sky and balances the
  channels.

Nothing here touches `composite.npy`; every value recomputes the working image
from the linear data, so these choices stay reversible.

### Calibration frames

Master dark / flat / bias / dark-flat frames are built as a per-pixel median and
cached. Each light is calibrated on the mosaic before debayer
(`(light - bias - dark) / flat`), and a bad-pixel map (hot pixels from the dark,
dead pixels from the flat) drives the **cosmetic correction** that replaces each
flagged pixel with a same-Bayer-phase neighbour median.

### Folder-watch ingest

Point `stacking_watch_dir` at a directory and MyAstroShine ingests frames dropped
into it automatically. When the folder goes idle for `stacking_watch_idle_minutes`
it can auto-stack (`stacking_watch_auto_process`). The current watch stack is
offered on the stacking screen without a URL. Good for a capture rig writing subs
in real time.

## External ML engines

Star removal and denoise can optionally run through **StarNet2** and **DeepSNR**
instead of the built-in classical code. **MyAstroShine bundles neither** - the
operator installs the binary, mounts it into the containers, and points a setting
at it. Once a working engine is configured it appears as a per-edit toggle
(StarNet2 in the **Stars** step, DeepSNR in the **Detail** step), and any failure
falls back to the classical path. Setup and licensing:
[DEPLOYMENT.md](DEPLOYMENT.md#external-ml-engines-optional) and
[THIRD_PARTY.md](../THIRD_PARTY.md).

## Presets

Five built-ins are always present: **Nebula**, **Galaxy**, **Deep Field**,
**Lunar**, **Cluster** (translated, not deletable). Save your own from the
**Export** step (up to 50); a user preset carries a delete affordance in the
chip list.

## AstroDex integration

From a photo in MyAstroBoard's AstroDex, **Send to MyAstroShine** opens the
editor here with a signed one-time handoff; the backend verifies it and pulls the
image itself. Edit as normal, then **Send back to AstroDex** posts the result
back, where it is filed as a **new** picture on the same object - the original is
never replaced. MyAstroShine only ever calls out to the board, so it works even
when the board is behind a reverse proxy. Standalone use needs none of this - the
integration is inert unless a webhook token and the board-origin allowlist are
configured. See [ARCHITECTURE.md](ARCHITECTURE.md#astrodex-integration).

## Themes and language

Light theme is the default; a footer control switches System / Light / Dark. The
interface is available in **English and French** - a header selector, defaulting
to the browser language on first load. (Image processing is language-independent;
a few backend detail strings stay English.)

## Settings

Everything tunable lives in **Settings** in the UI and persists under the data
volume - no `.env` editing, no restart (except `cors_origins`). The tabs:
**General** (upload cap, session lifetime, preview size, stacking limits and
workers, folder-watch), **Webhooks** (AstroDex tokens and allowlist),
**Advanced** (CORS, rate limits, log levels, external ML engine paths), and
**Logs** (tail, filter, clear, export a ZIP for a bug report). Full table:
[DEPLOYMENT.md](DEPLOYMENT.md#runtime-settings-edited-in-the-ui).
