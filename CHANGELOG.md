# Changelog

All notable changes to MyAstroShine are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project aims to
adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **A stacked FITS (or a 16-bit PNG/TIFF) now opens as a composite session**, the
  same as the multi-frame stacker's own output, instead of a one-shot 8-bit
  auto-stretch on upload. The editor's linear **Stack** step - background
  extraction, colour calibration, a tunable deep stretch - runs on the 32-bit
  data on every render, and the faint signal is never quantised to 256 levels on
  the way in. A Seestar / alt-az live stack's field-rotation + vignette border
  (the "red top / marked corners") is detected from the pixels and trimmed on
  ingest. `POST /api/upload` returns `is_stack: true` for these. See
  `docs/ALGORITHMS.md` "Upload ingest" and `app/services/linear_upload.py`.
- **Background extraction gains a frame-edge residual correction.** After the
  degree-2 polynomial it adds back the object-free sky residual, smoothed and
  masked to the frame border, so the sharper edge/corner colour cast a
  paraboloid can't bend to (a Seestar footprint the crop only partly removes) is
  taken too - while a galaxy halo or a frame-filling nebula in the interior is
  left exactly as before.
- A 3-plane (RGB) FITS that still goes through `decode_image` (an AstroDex
  handoff, say) is stretched with one shared, colour-preserving transform and a
  deep sky target, not three independent per-channel stretches that lifted the
  sky to a milky grey and rebalanced the colour.
- **The white-balance Temperature slider snaps to standard Kelvin stops**
  (2000 / 3200 / 4500 / 5500 / 6000 / 6500 / 7000 / 7500 / 8000 K) instead of a
  free 50 K ramp, and the readout names the tone ("Neutral · 6500 K"). Lower K
  warms the image, higher K cools it - the hint said the opposite and is fixed.
  The backend still accepts any value in range; an older preset's off-stop value
  shows verbatim with the thumb on the nearest stop.
- **Each editor slider gets a one-step revert.** The value a slider held before
  your current run of edits is remembered, and a small back-arrow appears next
  to that slider (only the one you're adjusting) to put it straight back. Cleared
  by a preset, a section reset, or a milestone restore.
- **Vignette is now signed (-100..100).** Positive still brightens the corners
  (lens-vignetting correction); negative darkens them - to deepen a vignette for
  effect, or tame an over-corrected stack.

### Fixed

- A trailing slash on a **CORS origin** or **AstroDex callback allowlist** entry
  in Settings is now stripped on save (`https://host/` -> `https://host`). A
  pasted slash previously made the entry silently match nothing - the CORS
  origin never carries one and the allowlist is checked against a slash-stripped
  `callback_base`. The allowlist match also now enforces a path boundary, so
  `https://board.example` no longer also authorises `https://board.example.evil`.
- **Editor sliders and tone curves now render on release, not on a timer.**
  Dragging slowly, or pausing mid-drag, no longer kicks off a render before you
  let go - the value tracks live and the pipeline runs on pointer-up / key-up
  (with a 1.2 s fallback if a release event never arrives).

## [0.4.0] - 2026-09-09

### Changed

- **AstroDex integration rebuilt around a signed handoff.** MyAstroBoard now
  opens the editor with a single `?handoff=` token; the backend verifies it,
  pulls the source image from the board itself, and drops you straight into the
  editor. The Export step gains **Send back to AstroDex**, which posts the
  processed image back as a signed `multipart/form-data` request - the board
  files it as a **new** picture on the same object, never a replacement. This
  instance is never contacted *by* the board, only ever calls *out* to it, so
  the flow works whether the board is on the LAN or behind a reverse proxy. The
  handoff token is HMAC-SHA256 signed with a webhook token's `signing_secret`,
  expires after 12 h, and is single-use for the return. See `docs/API.md`
  "AstroDex integration" and `initial_plan/PASSATION_MYASTROBOARD_INTEGRATION.md`.

### Removed

- The never-wired push endpoints `POST /api/astrodex/receive` and
  `POST /api/send-to-astrodex` (and the `AstroDexService` / `AstroDexDispatch`
  services), replaced by the handoff routes above. `astrodex_links` is reshaped
  by migration `d4e5f6a7b8c9`; `astrodex_callback_urls` /
  `astrodex_max_retries` / `astrodex_retry_delay_seconds` are unchanged.

## [0.3.0] - 2026-09-09

### Added

- Star removal (starless): the editor's **Stars** step now offers two ways to
  handle stars, grouped and explained side by side - **Reduce** (shrink each
  star in place, the existing control) and **Remove**. Raise **Remove stars**
  and the pipeline splits: the stars are pulled out right after the background
  corrections, every creative adjustment (tone, curves, colour, detail) then
  works on the nebula alone, and **Bring stars back** screen-blends them in at
  the end (0 keeps the image starless, 100 restores them full strength).
  Detection (sensitivity / max size, mask preview) is shared by both. The
  reconstruction is classical - a median-blur estimate on a downscaled copy,
  sized so galaxy and nebula cores are preserved - with no ML model and no new
  dependency (it also let `scikit-image`, unused since the v0.2 star-detection
  rebuild, be dropped). A very dense Milky Way star field is the known limit of
  the classical method; the **StarNet2 engine** below is the way past it.
- Optional ML engines for star removal and noise reduction, **installed by the
  operator, never bundled**. Point Settings -> Advanced at a
  [StarNet2](https://starnetastro.com/) and/or DeepSNR binary you mount into the
  containers and the editor gains an engine toggle: **StarNet2** in the Stars
  step (per-edit, replaces the classical split for the run) and **DeepSNR** in
  the Detail step's denoise control (runs early, before the tone stretch). Each
  is arm's-length - MyAstroShine writes a TIFF, runs the tool, reads the result
  back - and any failure (missing binary, timeout, bad output) logs and falls
  back to the classical code, so a client can always request them. A pass streams
  its progress onto the editor bar; the result is cached per session so a
  creative-only tweak doesn't re-run it. Nothing ships in the image and no
  Python dependency is added - see `docs/DEPLOYMENT.md` "External ML engines" and
  `THIRD_PARTY.md` (the tools are non-commercial; the operator accepts their
  terms).
- Edit milestones: a timeline under the preview where you can save the current
  adjustments (sliders, curves, framing, and the Depth Shift focal point) as a
  checkpoint and click back to it if you push an edit too far. The first
  milestone is always the original image. Milestones live only in the browser
  for the image being edited - loading another photo starts over, and there is
  no server-side copy.
- Light theme, now the default, matching the MyAstroBoard visual charter (deep
  teal primary accent, amber ecosystem accent, frosted panels over a lightly
  teal-tinted ground). The dark theme is unchanged.
- A **Theme** control in the footer - System / Light / Dark. "System" follows the
  operating system's light/dark setting and updates live when it changes. The
  choice is remembered per browser.
- The upload screen now shows real progress: a percentage and bar while the file
  transfers (over `XMLHttpRequest`, which `fetch` can't report), then an
  indeterminate "Preparing your image…" spinner while the server decodes it -
  previously a large FITS / RAW upload just sat with an unchanged button.
- `GET /api/config` - a small public endpoint exposing the runtime limits the UI
  needs before a session exists (the upload size cap, stacking limits). The
  upload screen's size hint and its pre-flight check now follow the operator's
  configured `max_image_size_mb` instead of a hardcoded 100 MB.
- Stacking rebuild (in progress): multi-frame stacking is being reworked to run
  on linear, full-bit-depth data instead of stretched 8-bit previews - the old
  pipeline was never run on real data and produced a near-black result on a real
  Seestar set. This release lays the foundation: a unified linear ingest (FITS
  Bayer mosaics kept intact and debayered in-pipeline, camera RAW demosaiced
  linearly, 8-bit previews sRGB-linearised), a `.zip` archive upload so a
  thousand-frame session is a handful of requests, per-frame thumbnails, and a
  frame-by-frame include/exclude toggle (`POST /api/stack/{id}/frame/{i}/exclude`)
  for dropping a sub with a trail or cloud. Frames now upload in batches
  (`POST /api/stack/{id}/upload-frames`) or as a `.zip`
  (`POST /api/stack/{id}/upload-archive`) instead of one request per frame, and
  the frontend checks the frame count against the instance limit before starting
  so you get a clear message, not a raw error. The stacking screen is reworked
  into a collect -> upload -> review -> stack flow: a drag-and-drop zone matching
  the single-image one (accepted formats, size limit), then frames upload as a
  batch and a thumbnail grid lets you click any frame to preview it large and
  tick a box to drop a trailed or clouded sub. After stacking you can still tweak
  a setting or exclude another frame and hit **Re-stack**
  (`POST /api/stack/{id}/process` now takes an optional settings body) with no
  re-upload, or inspect a frame and go "Back to composite". A `beforeunload`
  guard stops a mis-swipe or a mouse "back" from losing an in-progress stack.
  The pipeline now **registers** the frames - it detects stars, picks the
  sharpest frame as the reference and asterism-matches the rest onto it (a
  vendored triangle matcher, no new dependency), warps them with Lanczos,
  normalises each to the reference, and combines with iterative sigma rejection
  and noise weighting, all in bounded memory (a `float16` memmap + row tiling,
  so a thousand-frame stack does not need a thousand frames of RAM). On a real
  150-frame Seestar set: sub-pixel alignment, ~8.7x noise reduction. It now also
  **calibrates** each frame: upload master **darks, flats, bias and dark-flats**
  (`POST /api/stack/{id}/calibration/{kind}/frames`) and the pipeline builds a
  median master of each, applies `(light - bias - dark) / flat` on the Bayer
  mosaic before debayer, and repairs hot / dead pixels from the master
  dark/flat with a neighbour median (the honest replacement for the removed
  "cosmic ray" step; toggle with **Repair hot & dead pixels**). The Bayer
  mosaic is now debayered with an **edge-aware interpolating** demosaic at full
  resolution for the align/combine passes (registration still measures on the
  cheap half-res superpixel). Every sub is now **scored** (star count, FWHM,
  roundness, sky background, SNR) and the worst are **auto-rejected**: the
  **Auto-reject bad frames** setting (off / lenient / moderate / strict, default
  moderate) drops a clouded, soft, trailed or dawn sub before it can pollute the
  stack, the frame grid shows each sub's score and why it was dropped, and
  unchecking a frame rescues it from the filter on the next run. `weighting:
  "quality"` now uses that same score. The finished composite is **cleaned up**
  before it opens in the editor (**Clean up the composite**, on by default): the
  field-rotation edges are cropped away, a low-order sky-gradient is subtracted
  (a degree-2 fit that cannot carve into a nebula), and the colour is
  neutralised and balanced. Combined with a better reference-frame choice (the
  middle of the session, not the frame with the most stars) a real 100-sub set
  now comes out framed on the target with a flat neutral background instead of
  noisy rainbow speckle. Finally, a stacked composite now opens the editor on
  its **32-bit linear data**, with a new **Stack** step (composite sessions
  only): a **Stretch** control that sets the auto-stretch strength, a
  **Background extraction** slider, and a **Colour calibration** toggle - all
  non-destructive, recomputed from the linear composite so nothing is lost to an
  early 8-bit quantisation. The whole creative pipeline (`ImageProcessingService`)
  now runs in float32 internally and quantises only at the encode boundary, which
  also benefits single-image FITS/RAW edits. Only the field-rotation crop is
  baked into the saved composite; background extraction and colour calibration
  moved out of the one-shot cleanup and into the Stack step. 
- Stacking scale & UX: the progress bar now shows which frame each step is on
  ("Aligning 340 / 1066"), not just a percentage. The register / align / combine
  passes run on a **thread pool** (auto-sized to the CPU count, capped at 4,
  tunable in Settings) - roughly 2x faster on a real multi-frame stack, and
  parallelising the combine step is what moved the needle. An interrupted run now
  **resumes**: the aligned frames and a small plan file survive a crash, so a
  retry - or a re-stack that only changes the combination / rejection / weighting
  - skips straight to the combine step instead of re-registering everything. And
  a **watch folder**: point the worker at a directory (Settings) and frames
  dropped there are ingested into a rolling stack that auto-processes once the
  folder goes quiet; the stacking screen shows a banner to open it.
- **Drizzle** (Fruchter & Hook) as an opt-in stacking option (2x / 3x). Each
  input pixel is a shrunken "drop" mapped through its registration transform and
  area-distributed onto a finer output grid, so a large, well-dithered stack
  (the Seestar's alt-az field rotation supplies the dither) yields real
  resolution gain a plain resample cannot. It runs as an extra pass after the
  normal stack (which stays the fallback and the outlier reference), is slower
  and correlates neighbouring-pixel noise, and is off by default.

### Changed

- The language switcher moved from the header to the footer, next to the new
  theme control; the header now carries only the brand and Settings.
- Denoise and Chroma denoise now use the documented bilateral-filter range
  (diameter 5-20, sigma 75-150) so high slider values deliver the intended
  stronger noise cleanup on deep-sky frames.
- Built-in deep-sky presets were rebalanced to darken shadows instead of
  lifting them (Galaxy `shadows: -0.25`, Deep Field `shadows: -0.35`) for
  better object-vs-background separation, matching the Auto Astro strategy.
- The per-IP request rate limit now defaults to 600/min (was 120) and can be
  set as high as 6000 - it is an abuse guard for a public instance, not a
  fairness knob, and a single user editing plus running a stacking session
  should never hit it.
- Consistent card surfaces across the editor, Settings, and stacking: the
  editor's three columns (workflow rail, inspector, preview), the Settings nav
  and content panes, and the stacking result blocks now use one framing system
  instead of three ad-hoc ones. The preview image is matted with its histogram
  in a single card.
- The stacking screen now uses the same shape as the single-image editor: a
  clean centered upload block first, then - once frames are in - a left workflow
  rail (Frames / Calibration / Settings / Result), the active step's controls in
  the inspector, and a persistent preview with the frame grid. Previously the
  settings and calibration panels sat in a right-hand sidebar shown from the
  start.
- Stack storage is much lighter: uploaded frames are now kept at their source
  bit depth (a 16-bit camera frame as uint16, not float32) - **half the disk**,
  bit-exact. A new **Stack retention** setting (default 12 h, separate from the
  session lifetime) bounds how long a stack's frames are kept for re-stacking;
  the composite it produces still lives the full session lifetime. The hourly
  cleanup now also sweeps abandoned uploads (frames in, never stacked) after
  4 h, orphaned align buffers left by a killed run (a thousand-frame run leaves
  ~10 GB), and stack directories with no database row.
- The database schema is now brought to head automatically on API and worker
  startup (`alembic upgrade head`); a fresh database is built from the
  migrations. Previously a schema change needed a manual `alembic upgrade` and a
  lagging dev database silently broke the cleanup task. Startup now also
  **verifies the columns against the models** after the upgrade: a SQLite dev
  database missing a column (a migration edited after it ran) is repaired in
  place with a loud log line, and any other backend refuses to start with a
  clear message instead of failing later with a cryptic `no such column`. A new
  `tests/db/test_migrations.py` fails CI if the migrations and the models drift
  apart at all. (`stacks.drizzle_factor`, which had been appended to an
  already-applied migration, is split into its own idempotent revision.)
- The development stack now defaults to `PROCESSING_MODE=queue` - a long job (a
  thousand-frame stack) runs on the Celery worker instead of blocking the single
  API process for its whole duration - and `POST /api/stack/{id}/process` no
  longer holds the event loop even under `sync`.
- Multi-frame upload is **~4x faster** and no longer freezes the API while it
  runs: each batch is decoded and thumbnailed across a threadpool (the per-frame
  thumbnail is built from a downscaled copy - the auto-stretch over a few
  thousand pixels looks the same as over two megapixels and is ~9x cheaper), and
  a batch is one database commit instead of one per frame.
- New application logo: the header now shows the MyAstroShine icon, and the
  browser-tab favicon is a matching amber-star-and-orbit mark.

### Removed

- `scikit-image` is no longer a dependency - it had been unused since the v0.2
  star-detection rebuild switched off `skimage.feature.blob_dog`, and the new
  star-removal estimate is pure OpenCV.
- Stacking's `sift`/`orb` alignment, `median`/`mean`/`sigma_clip` combination
  and the cosmic-ray toggle are replaced by a transform model
  (`translation`/`similarity`/`affine`), `average`/`median` combination, a pixel
  rejection algorithm and a frame-weighting mode. The `stacking_detector`,
  `stacking_combination_default` and `stacking_cosmic_ray_threshold` settings are
  gone; `stacking_max_frames` now defaults to 2000 (a real imaging night at 10 s
  subs), up from 100.

### Fixed

- The stacking composite preview no longer comes out as noisy rainbow speckle
  with the target barely visible. The linear stack is now shown with the sky
  background neutralised and **one shared stretch** for all three channels
  (derived from the luminance, a lower background target so read noise stays in
  the shadows) instead of a per-channel auto-stretch that turned the channel
  imbalance into chroma noise. A real background model / colour calibration is
  still a post-stack step - the preview is a sane first look, not the finished
  image.
- The registration reference frame is chosen better: the frame nearest the
  **middle of the session** with a typical star count and good sharpness, not
  simply the one with the most stars. On an alt-az mount the most-stars frame is
  often an outlier pointing (a cluster drifted to centre, a transparency spike);
  using it shrank the aligned footprint and pushed the target into a corner.
- Stacking in the default sync processing mode left its job record stuck at
  "queued" forever - a few stacks (or re-stacks) in a session would trip "Too
  many concurrent processing jobs" and stay tripped. Sync-mode stacks now mark
  the job completed/failed the same way the queue path does.
- With `PROCESSING_MODE=queue` (the Docker default), applying a preset or **Auto
  Astro**, or **re-stacking** an already-finished stack, took two clicks: the
  first appeared to do nothing (or flashed the previous result). The backend
  answers before the worker has run, and these callers assumed the response
  meant "done" - so the preview never refetched. Preset apply and Auto Astro now
  follow the job to completion over the WebSocket (the same way a slider edit
  does), and `POST /stack/{id}/process` reports `processing` for the new run
  instead of echoing the previous run's `completed`.
- A burst of slider edits could wedge the editor: the preview stopped updating,
  the API log filled with `QueuePool limit ... connection timed out` (a 500 on
  the next `/process`), and every change then landed at once. The progress
  WebSocket held a pooled database connection open for its whole lifetime, so a
  handful of concurrent sockets (one per queued job) exhausted the pool. Fixed:
  - the WebSocket reads the job once with a short-lived session and holds **no
    connection** while it streams, and on an idle tick it re-reads the DB, so a
    terminal event lost by Redis (or published before it subscribed) still
    closes the socket instead of hanging the client;
  - the editor keeps **at most one `/process` in flight per session** and
    coalesces the rest, so a drag becomes two jobs, not twenty (and if that one
    job goes silent for 45 s, a new edit proceeds rather than waiting forever);
  - a job a newer edit **supersedes now bails out at the next pipeline stage**
    instead of running to completion, and `superseded` is pushed to the socket
    at once so it closes.
- `docker-compose.dev.yml` sets `WATCHFILES_FORCE_POLLING` so `uvicorn --reload`
  actually picks up backend edits over a Docker Desktop bind mount on
  Windows / macOS (the web service already polled for HMR).
- The editor no longer 429s itself ("Too many concurrent processing jobs") when
  you move several sliders quickly: a new `/process` for a session now retires
  any still-pending job for that same session (status `superseded`) before it
  starts, instead of letting a queue of obsolete jobs pile up against the per-IP
  concurrency budget. The frontend also drops the previous job's WebSocket
  rather than leaving it to reconnect in the background.
- A stacked composite that is portrait (or any non-16:9 shape) no longer opens
  in the editor as a thin strip in a black frame - the preview reads the real
  aspect ratio off the image when the caller doesn't provide dimensions.
- The before/after divider now tracks the pointer (and the actual split of the
  image) while the preview is zoomed in; it was computed in unscaled container
  coordinates and drifted from the visible seam at any zoom above 100%.
- The stacking progress-event stream no longer opens a fresh Redis connection
  per event (a thousand-frame stack emits hundreds).

### Known gaps

- `depthShiftIntensity` (a `ProcessingParameters` field with its own slider) is
  dead - nothing in the enhancement pipeline or `depth_shift.py` reads it, and
  the Depth Shift viewer keeps its own separate intensity state. Needs a product
  decision (most likely: wire it as that viewer's starting value), not a copy
  change.
- `PROCESSING_MODE=queue` on Docker Desktop runs SQLite without WAL (its
  shared-memory file does not work over a bind mount), so the API and worker
  share one lock. Fine for a single operator; set `DATABASE_URL` to Postgres
  before scaling the worker out.

## [0.2.0] - 2026-09-06

### Added

- Star reduction rebuilt on per-star detection (`StarDetectionService`, a
  thresholded top-hat + `cv2.connectedComponentsWithStats`, at native
  resolution, robust to ordinary sensor/JPEG noise) instead of a single
  image-wide top-hat mask, so only genuine stars are shrunk and diffuse
  nebulosity is never dimmed. Each star shrinks via erosion floored at its
  own local background, so it can't crush to a black dot or bloat into a flat
  pale disc at full strength. New `star_sensitivity` / `star_max_size`
  parameters tune what counts as a star.
- Star mask preview: `POST /api/star-mask/{session_id}` reports detected star
  positions for a live "N sources detected" overlay in the editor, toggled from
  the Stars panel.
- Auto Astro: a one-click "Auto Astro" button (`POST /api/auto-astro/{session_id}`)
  analyses the image's histogram and star density and applies a computed
  starting parameter set - crushing the background for depth/separation from
  the DSO, and a gentle, log-scaled star reduction that stays a sensible
  starting point across both sparse frames and busy deep-stacked fields -
  in place of manually dialing in every slider. Auto Astro and preset apply
  both keep the session's current framing (crop / rotate / straighten / flip)
  rather than resetting it - a look is not a composition.
- Editor UX: a workflow-driven three-pane editor. A numbered **rail** on the
  left steps through the retouching order (1 Framing, 2 Background, 3 Light,
  4 Curves, 5 Colour, 6 Detail, 7 Stars, 8 Depth), bracketed by a
  one-click **Start** (Auto Astro + presets) and **Export** - the same order
  the backend pipeline applies. Only the selected step's controls show, in an
  **inspector** panel with its own help text, reset, and a "Next" link; the
  **preview + histogram stay pinned** on the right instead of scrolling out of
  view under a long list of tools. A step shows a dot on the rail once its
  values leave the default. Crop / straighten / rotate / flip is now step 1,
  edited directly on the preview (the separate full-screen crop editor is
  gone). White balance (temperature / tint) moved from the creative colour
  controls into step 2, next to the other background corrections, matching the
  pipeline. A focal-point picker on the preview (click to set) drives where
  the Depth Shift parallax centers - `focus_point` was accepted by the API
  before this but never used.
- A **"New photo"** button on the editor returns to the upload screen -
  previously the only way back was a full reload. Leaving with unsaved edits
  (the button, or a browser back / reload / mobile edge-swipe) now asks first,
  so a mis-swipe on a slider no longer silently loses the work. The mode
  switcher is hidden while a photo is open.
- i18n: FR + EN. Every frontend-owned UI string now goes through
  `useTranslation()`'s `t()`, backed by `frontend/src/i18n/translations/{en,fr}.json`
  (`en.json` is the reference language); a compact EN/FR selector sits in the
  header. Detects the browser language on first load, then persists the
  choice client-side. `scripts/validate_i18n.py` (new CI job) checks key
  parity, leaf types, and `{placeholder}` names between the two files.
  Backend-owned *detail* strings (log lines, specific error text) stay
  English-only, but the five built-in preset names / descriptions and a few
  whole classes of API failure (server busy, temporarily unavailable, 5xx)
  are now shown in the user's language.
- Permanent page footer (name, version, GitHub link - inspired by
  MyAstroBoard's own footer bar), replacing the version number that used to
  sit in the header. In-app update check folds into it: once a newer GitHub
  release is published, a discreet second line appears with a link to it and
  a "What's new" that opens the release notes in a modal, rendered from
  markdown (headings, bold, lists, links) rather than shown as raw
  `### `/`**` syntax. `GET /api/version/check-updates` (`VersionCheckService`)
  queries GitHub's releases API and caches the result in memory for 4 hours,
  so the frontend's 4-hourly poll can never translate into hitting GitHub's
  rate limit; every failure path (timeout, GitHub's own rate limit, a
  malformed response, ...) degrades to no notice rather than an error. The
  frontend re-verifies the version comparison itself before showing
  anything, so a stale/incorrect cache can never present as a downgrade.
- Tone curve editor: an interactive curve graph (drag points to reshape,
  double-click to add or remove a point) alongside the adjustment sliders.
  Backed by a new `curve_points` parameter and a monotone cubic Hermite
  spline LUT stage in the processing pipeline, so a handful of dragged
  points make a smooth curve - not a faceted polyline - and can never
  overshoot past a control point's value into crushed shadows or blown
  highlights.
- Five missing core astro ops, a new **Corrections** section, and split
  tone controls:
  - **Vignette correction** - brightens the corners to counteract lens
    vignetting (a generic radial model, not a per-lens calibrated profile).
  - **Gradient reduction** - flattens smooth background gradients (light
    pollution, sky glow) via a large-blur background estimate, subtracted
    back out.
  - **Dehaze** - dark-channel-prior haze removal, restoring contrast/colour
    lost to a veiling glow or light-pollution haze.
  - **Colour noise reduction** - denoises only the Cr/Cb colour channels,
    leaving luma (and its own separate `denoise` control) untouched -
    colour speckle tolerates far more smoothing than brightness detail does.
  - **Whites / Blacks** - push the white/black clipping points, narrower
    and more aggressive than the existing Highlights/Shadows (only the true
    near-white/near-black tail moves, not the broader upper/lower-mid
    range) - the usual distinction in most photo editors.
  - Vignette correction, Gradient reduction and Dehaze live in the editor's
    step 2 (**Background**), applied before any creative grading.
- **FITS + 16-bit + camera RAW upload support** - previously 8-bit JPEG/PNG/
  TIFF only (and a 16-bit TIFF/PNG was silently truncated to 8-bit). FITS
  (`.fits`/`.fit`/`.fts`) and camera RAW (`.cr2`/`.cr3`/`.nef`/`.arw`/`.dng`/
  `.orf`/`.rw2`/`.pef`/`.raf`) now decode via `astropy`/`rawpy` respectively.
  FITS and a genuine 16-bit TIFF/PNG both get a new auto-stretch (the same
  "screen transfer function" PixInsight/Siril use) instead of a naive bit-
  shift; RAW is demosaiced with the camera's as-shot white balance. See
  `docs/ALGORITHMS.md` "Upload ingest: FITS / RAW / 16-bit".
- **Colour curves** - the Tone Curve panel now has 4 tabs (RGB / Red / Green /
  Blue), each an independent curve on the same `curve_points_to_lut`
  monotone-spline LUT the master RGB curve already used, applied via
  `cv2.split` / `cv2.LUT` per channel / `cv2.merge` instead of identically to
  all three. For a colour cast a single white-balance gain can't reach at one
  specific tonal range (e.g. a green background-sky cast only in the
  midtones), or deliberate colour grading. New `red_curve_points` /
  `green_curve_points` / `blue_curve_points` parameters (same empty-by-default,
  first-at-0/last-at-255 validation as `curve_points`), applied right after
  the master curve. See `docs/ALGORITHMS.md` "Colour curves".

### Changed

- `brightness` renamed to `exposure` throughout the API, Auto Astro, and the
  editor UI - no behaviour change, just a name matching the rest of the
  "Exposure/Highlights/Shadows/Whites/Blacks" tone-control family this
  release completes. A saved preset or automation using the old
  `brightness` key needs updating to `exposure`.
- Full-resolution enhance's performance budget raised from 5s to 8s
  (`tests/benchmarks/test_processing_speed.py`) to account for the 5 new
  pipeline stages above - measured 5.75s on a 24MP frame with every slider
  active at once (an unrealistic worst case; the interactive preview budget,
  what a slider drag actually feels like, is unchanged and unaffected).

### Removed

- The `denoise_enable_ml` / `depth_detection_method` Settings fields (and
  their "Processing" section) - both were placeholders for ML backends
  evaluated this release and not adopted (see `docs/ALGORITHMS.md` "Depth
  map" and "ML denoising"): no viable pretrained denoising model exists to
  point a self-hoster at, and MiDaS/DPT-Hybrid depth estimation produces a
  near-featureless result on real astrophotos regardless of model size.
  Neither field ever did anything - `depth_detection_method` had no reader in
  `DepthMapService`/`DepthShiftService` even before this evaluation. An old
  `app_settings.json` with these keys still loads fine; they're just ignored.
- The `depth_shift_intensity` processing parameter and its unused
  `ProcessRequest.apply_depth_shift` companion - dead since they were added
  (no pipeline stage ever read them; the Depth Shift viewer has always kept
  its own intensity state). `ProcessingParameters` now silently drops the
  retired key on the way in, so a stored preset from an older version still
  loads instead of hitting `extra_forbidden`.
- Dead-code sweep before the release: the unused `useAstroDexIntegration`
  hook is now wired to the "Send to AstroDex" button (which gains
  sending / sent / error feedback); the unused `react-router-dom` dependency
  (routing is hand-rolled hash-based), the unreachable `UpstreamUnavailableError`
  exception, the never-called `StorageService.count_stack_frames`, the unused
  `API_PORT` constant, and the unused `get_astrodex_service` DI wrapper are gone.

### Fixed

- A processing job that got stuck non-terminal (a worker died mid-run, or a
  queued job was never picked up) counted against the per-IP concurrency limit
  forever - a few stuck rows would eventually make every enhance / Auto Astro
  fail with "Too many concurrent processing jobs". Such a job now stops
  counting once it is older than `STALE_JOB_SECONDS` (15 min, well above any
  real operation), and the hourly cleanup marks it failed for good
  (`JobService.cleanup_stale_jobs`).
- Expired multi-frame stacks were never cleaned up - only the composite
  session they produce was. `StackRecord` rows and their uploaded frame PNGs
  under `DATA_DIR/stacks/` now expire on the same hourly schedule as sessions
  (`StackingService.cleanup_old_stacks`), so a long-running instance doesn't
  accumulate them forever.
- `GET /api/presets` 500ing whenever a built-in preset stored before a
  `ProcessingParameters` field rename (e.g. this release's `brightness` ->
  `exposure`) no longer matched the current model (`extra_forbidden` on the
  stale field). `PresetService.ensure_defaults()` now refreshes existing
  built-in presets to match the current spec on every call, not just inserts
  missing ones - built-ins are fully code-defined and never user-edited, so
  any drift is always wrong data, never a customization worth preserving.
  `is_favorite` (the one user-set field on a built-in) is left untouched.
- The `worker` container always reporting Docker-unhealthy - it inherited the
  image's HTTP healthcheck (`curl :8002/api/health`) from the shared
  Dockerfile stage, but a Celery worker never serves HTTP. Both compose files
  now give `worker` its own healthcheck (`celery inspect ping`).

## [0.1.0] - 2026-09-04

First implementation pass covering the full v1.0 + v1.1 roadmap. Nothing has been
tagged yet.

### Added

#### Core enhancement (Sprint 1-3)

- Image upload with format/size validation, 512 px preview generation, per-channel
  histogram, and session tracking (`POST /api/upload`, `GET /api/preview/{id}`).
- `ImageProcessingService` pipeline: geometry (rotate / flip / straighten /
  crop), white balance (temperature/tint), contrast, brightness,
  highlights/shadows recovery, saturation, vibrance, clarity, denoise
  (bilateral), star reduction (top-hat star mask + morphological erosion),
  sharpness. Validated against documented bounds.
- `POST /api/process/{id}` applies parameters and returns a job handle.
- `GET /api/health` system health check.
- Alembic migration scaffolding; `init_db()` creates tables for local/dev use.

#### Job queue and progress (Sprint 3)

- `PROCESSING_MODE` setting: `sync` (run in the request, default) or `queue`
  (Celery task on Redis).
- Celery app and tasks (`task_process_image`, `task_process_stack`,
  `task_cleanup_sessions`); `task_always_eager` under `APP_ENV=test`.
- `JobRecord` tracking with per-step progress; Redis pub/sub bridge.
- `WS /ws/processing-status/{job_id}` and `WS /ws/stack-status/{job_id}`: DB
  catch-up on connect, then live relay until a terminal status.

#### Presets (Sprint 3)

- `PresetService` with five built-ins (Nebula, Galaxy, Deep Field, Lunar,
  Cluster); built-ins cannot be deleted.
- `GET/POST /api/presets`, `DELETE /api/presets/{id}`,
  `POST /api/presets/{id}/apply/{session_id}`.
- Duplicate-name and quota (50 user presets) guards.

#### Depth Shift (Sprint 4)

- `DepthMapService`: Sobel-gradient depth map, normalization/smoothing, depth
  statistics.
- Parallax layer generation (2-12 BGRA layers, far to near).
- `POST /api/depth-shift/{id}`, plus metadata, depth-map, and per-layer endpoints.

#### AstroDex integration (Sprint 4)

- `AstroDexService`: canonical-JSON HMAC-SHA256 signing, payload composition,
  retry with exponential backoff on 5xx.
- `POST /api/astrodex/receive` (inbound image) and `POST /api/send-to-astrodex`
  (outbound signed webhook, delivered in the background).
- Long-lived bearer webhook tokens with per-token signing secrets, created and
  revoked from the Settings UI (`GET/POST /api/tokens`, `DELETE /api/tokens/{id}`).
- Callback-URL allowlist (`ASTRODEX_CALLBACK_URLS`).

#### Stacking (Sprint 6-7)

- `RegistrationService`: SIFT/ORB keypoints, Lowe ratio test, RANSAC homography,
  perspective warp.
- `NormalizationService` (background-level equalization) and `CosmicRayService`
  (MAD-based robust sigma rejection with an absolute-deviation floor).
- `CombinationService`: NaN-aware median, mean, and iterative sigma-clip;
  SNR-improvement estimate (~sqrt(N)).
- `POST /api/stack/initiate`, `POST /api/stack/{id}/upload-frame`,
  `POST /api/stack/{id}/process`, `GET /api/stack/{id}`. The composite is a normal
  session and can be enhanced, previewed, and downloaded.

#### Frontend

- React 19 + TypeScript + Vite single-page app, Tailwind CSS v4 (CSS-first).
- "Darkroom / neutre pro" design system (`docs/DESIGN.md`): semantic token layer
  and shared component classes (`.panel`, `.btn`, `.field`, `.slider`,
  `.segmented`, `.chip`, `.dropzone`) in `src/styles/index.css`. Dark-only.
- Single-image editor: drag-and-drop upload, before/after split preview with zoom
  controls, histogram, grouped parameter sliders (500 ms debounce), preset
  buttons, "save as preset" dialog, download.
- Parameter tooltips: each slider gets a small "i" badge (hover or keyboard
  focus, screen-reader linked via `aria-describedby`) explaining what it does.
- Crop / rotate tool (`CropTool`): full-screen mode with a draggable crop
  rectangle (corner + edge handles), straighten dial (+/-45 deg), 90 deg rotate,
  horizontal / vertical flip, and aspect presets (Free / Original / 1:1 / 16:9 /
  3:2 / 4:5 / 5:4). Commits a `geometry` object applied first in the pipeline.
- Preset chips: apply, plus a two-step delete on user presets (built-ins have no
  delete affordance; the backend also rejects it with 403).
- Interactive Depth Shift viewer (pointer-driven parallax, intensity slider).
- Multi-frame stacking mode: frame upload list, settings panel (alignment,
  combination, cosmic-ray/background toggles), step-by-step progress over the
  WebSocket, results panel with statistics, and "enhance composite" handoff.
- Webhook token manager (create with one-time secret display, revoke).
- AstroDex context detection from URL parameters and "send to AstroDex" action.
- snake_case <-> camelCase conversion isolated to the API/WS clients.

#### Tooling and infra

- `scripts/check_deps_fresh.py`: fails when any pin falls behind PyPI/npm; run in
  `pytest` and a weekly CI job.
- Docker Compose (`api`, `worker`, `web`, `redis`) and a hot-reload
  `docker-compose.dev.yml`.
- Playwright end-to-end suite (`npm run test:e2e`): upload -> slider -> process
  -> download, save-as-preset, and the full three-frame stacking flow with the
  "enhance composite" handoff. Boots the real backend and Vite dev server.
- GitHub Actions: backend (ruff, mypy, pytest), frontend (lint, typecheck, test,
  build), and e2e (Playwright) jobs, plus the dependency-freshness cron.
- API listens on port 8002.
- Initial Alembic revision (`606a1e113989_create_core_tables`) covering all six
  tables; `alembic upgrade head` / `downgrade base` and `alembic check` verified
  clean against the ORM models.

#### API rate limiting

- Per-IP request-rate limit (default 120/min, in-memory fixed window) on
  `/upload`, `/process/{id}`, `/presets/{id}/apply/{session_id}`, and
  `/stack/*`; over the limit returns `429 RATE_LIMITED`. (Shipped at the API
  spec's original 10/min first; raised the same day after it broke e2e and
  would have broken real interactive editing - the editor re-processes on
  every debounced slider change.)
- Per-IP concurrent-job limit (default 5), checked against the shared `jobs`
  table so it holds under both `sync` and `queue` processing modes.
- `rate_limit_enabled` / `rate_limit_per_minute` / `max_concurrent_jobs_per_ip`
  in Settings -> Advanced; `JobRecord.client_ip` (new Alembic revision
  `623faa14df02_add_job_client_ip`).

#### Session-cleanup scheduler

- `worker` runs Celery beat embedded (`-B`, both compose files): hourly,
  `task_cleanup_sessions` deletes sessions past `session_expiry_hours` and
  their files, regardless of `PROCESSING_MODE`. Schedule state persisted at
  `DATA_DIR/celerybeat-schedule`.

#### Performance benchmark suite

- `backend/tests/benchmarks/`: codifies the Success Metrics acceptance
  criteria as runnable checks - full-res (~24MP) enhance (measured 3.0s vs a
  5s budget), preview (512px) reprocess (38ms vs 500ms), and an empirical
  stacking-SNR check (16 synthetic frames with known noise through
  `combine(..., "mean")`, measured 3.99x vs a theoretical 4.00x). Opt-in
  (`RUN_BENCHMARKS=1 pytest tests/benchmarks --no-cov`) rather than part of
  the default suite, since wall-clock budgets are sensitive to the machine and
  to coverage instrumentation; runs weekly via
  `.github/workflows/benchmarks.yml`, not on every push/PR.

#### Release mechanics

- Root `VERSION` file is now the single source of truth for the app version
  (previously hardcoded separately in the backend and frontend); read via a
  build-time `APP_VERSION` / `VITE_APP_VERSION` Docker build argument, or
  straight from the file for local dev.
- **Single Docker image**: the root `Dockerfile` (multi-stage: Node builds
  the frontend, Python runs the API) replaces the previous two-image split
  (`backend/Dockerfile` + `frontend/Dockerfile` behind nginx). FastAPI now
  serves the built React SPA directly (`StaticFiles`, mounted after every
  `/api`/`/ws` route - the frontend's hash-based routing needs no
  SPA-fallback handling), with `GZipMiddleware` and the security response
  headers nginx used to add (`X-Frame-Options`, `X-Content-Type-Options`,
  `Referrer-Policy`) moved into `app/main.py`. A `target: backend` build
  (skips the frontend stage) serves `worker` and the dev `api` service, which
  never need the built UI. One less container, one URL (`:8002`) for
  everything instead of `:8002` (API) + `:3000` (nginx).
- `.github/workflows/release.yml`: tag-triggered (`v*.*.*`) multi-arch build
  and push of the one image to **both** `ghcr.io/myastroboard/myastroshine`
  and Docker Hub's `myastroboard/myastroshine`, a Trivy scan, and a GitHub
  Release generated from this changelog.
- `.github/workflows/post-release-cleanup.yml`: opens a PR that files this
  section under a dated release heading after a successful publish
  (`scripts/changelog_release.py`).
- `CODE_OF_CONDUCT.md`, `SECURITY.md`.
- `docker-compose.yml` gained `image:` alongside `build:` on `api` so a clean
  machine can `docker compose up` from the published image without cloning
  the repo; see `docs/DEPLOYMENT.md`.

### Changed

#### Configuration moved out of the environment (PASSATION alignment, part 1)

- `docker compose up` now needs no `.env` editing. The compose files carry only
  structural variables (`APP_ENV`, `DATA_DIR`, `PROCESSING_MODE`, the Redis URLs);
  `docker-compose.yml` dropped from 11 backend variables to 6 and holds no
  secrets.
- Single persistence root `DATA_DIR` (`/data` in the image). The database,
  session images, stacking frames, cache, log file, `secret_key.txt` and
  `app_settings.json` all derive from it; the two data volumes were merged into
  one (`myastroshine_data`).
- The session / HMAC-fallback secret is generated once into
  `DATA_DIR/secret_key.txt` (`secrets.token_hex(32)`) and never regenerated.
  `ASTRODEX_WEBHOOK_SECRET` is gone.
- New `app_settings.json` holds every runtime-tunable value (CORS origins,
  AstroDex callback allowlist and retry policy, upload limit, session lifetime,
  preview size, ML denoise, depth method, stacking defaults, log levels). It is
  edited from a rebuilt **Settings** screen (General / Webhooks / Advanced tabs)
  via `GET`/`POST /api/admin/app-settings`, gated by `ADMIN_ENABLED`.
- `app/config.py` now exposes only the deployment shape; product settings come
  from `app/utils/app_settings.py` (`get_app_settings()` / `save_app_settings()`
  / `reload_app_settings()`). `DATABASE_URL` stays as an optional override for
  Postgres.
- `docs/DEPLOYMENT.md` rewritten around this split (structural env table +
  "where to set it in the UI" table).

#### Settings is its own page

- Settings moved out of the editor into a standalone route (`#/settings`) with a
  section rail (General / Webhooks / Advanced), labelled rows with descriptions,
  toggle switches, and a sticky save bar. `useAppSettings` holds a draft and
  posts the whole object back.

#### Visual charter aligned with MyAstroBoard (PASSATION alignment, part 5)

- `docs/DESIGN.md` rewritten: the sky/teal primary accent (`#38bdf8`), the amber
  ecosystem accent (`#f59e0b`, used for AstroDex actions), deep navy-teal
  surfaces, a fixed background gradient with two ambient halos, and glass panels
  - the charter now shared with MyAstroBoard. The image still stays the loudest
  thing on screen.
- Token layer in `frontend/src/styles/index.css` reworked accordingly; new
  `amber*` tokens, `--gradient-accent`, `--shadow-glass` / `--shadow-premium`,
  and a `.btn-amber` modifier. `.btn-primary` is now the teal gradient. No
  component markup changed - everything is token-driven.

#### Logging: rotating file sink + admin controls (PASSATION alignment, part 4)

- `get_logger()` now renders through the stdlib, so alongside the console there
  is a rotating file at `DATA_DIR/myastroshine.log` (10 MB x 5) - and
  `worker.log` for the Celery worker. Line format carries the timestamp in the
  `TZ` zone with the UTC offset, the module, level, and `[func:line]`.
- Independent console and file levels (`console_log_level` default `warning`,
  `log_level` default `info`), changeable at runtime - `apply_runtime_log_levels`
  runs at startup and after any settings write; noisy libraries (`httpx`, `PIL`,
  ...) pinned to `warning`.
- New endpoints: `GET /api/admin/logs` (tail, newest first, `level` filter),
  `GET`/`POST /api/admin/logs/level`, `POST /api/admin/logs/clear`,
  `GET /api/admin/logs/export` (ZIP of the logs + rotations + worker log).
- Settings gains a **Logs** section: live tail, level filter, clear, export ZIP.

### Fixed

- Editor preview now refreshes after every adjustment: `useImageProcessing`
  exposes a `previewVersion` that the processed-image URL carries as a
  cache-buster (the URL was otherwise constant, so the browser kept the first
  render).
- Applying a preset now also moves the sliders to the preset's values
  (`syncParameters`), so a follow-up tweak starts from the preset; a manual
  slider edit (or Reset all) drops the preset highlight (`clearActivePreset`).
- Before/after divider: the whole frame is a grab zone with an `ew-resize`
  cursor and a centre handle; dragging no longer selects the page (images are
  `draggable={false}` / `pointer-events-none`, container is `select-none` and
  captures the pointer).
- Before/after view compares the true upload against the result:
  `GET /preview/{id}?original=true` serves the untouched original, and the two
  images share one box via `clip-path` so they stay aligned. The preview frame
  now takes the image's real aspect ratio instead of a fixed 16:9 letterbox.
  Once a crop/rotate/flip/straighten changes the result's frame, the "before"
  side switches to `?original=true&geometry=true`, which applies that same
  geometry to the original on the fly (no colour/tone enhancement) so the two
  stay aligned instead of the split disappearing.
- Depth Shift viewer is a centred modal (was an inline block pushed off-screen)
  and closes on Escape / backdrop click.
- Docker dev stack: Vite proxies `/api` and `/ws` to the `api` service
  (`VITE_PROXY_TARGET`), so backend-relative image URLs (depth layers, stacked
  composite) load instead of 502-ing. `VITE_API_URL`/`VITE_WS_URL` dropped from
  `docker-compose.dev.yml`; `ws.ts` builds an absolute ws:// URL from the page
  origin when unset.
- `mypy`: `packages = ["app"]` already kept the CI command (`mypy app`) from
  ever touching `tests/`, but an IDE's mypy integration analyzes whatever file
  is open regardless of that scoping, so every untyped pytest fixture/test
  function surfaced as a strict-mode error there. Added a `tests.*` override
  (relaxed the same way ruff already special-cases `tests/*`) - fixed ~130
  false positives; the handful of real ones left (a couple of loosely-typed
  numpy assignments, a duck-typed fake `Request` in the rate-limit tests) were
  fixed properly instead of suppressed.

### Security

#### Release-hardening pass

- AstroDex callback-URL allowlist now fails closed: an empty
  `astrodex_callback_urls` rejects every callback URL (previously it allowed
  any), closing an SSRF path through `/api/send-to-astrodex` and
  `/api/astrodex/receive`.
- `/api/tokens` and the previously-ungated `GET /api/admin/app-settings` /
  `GET /api/admin/logs*` now require `ADMIN_ENABLED` like their sibling write
  routes already did.
- `cors_origins` rejects a literal `"*"` entry - the API always sets
  `allow_credentials=True`, so a wildcard origin would be a real hole, not
  just a combination browsers already reject.
- Decoded image dimensions are capped (`MAX_IMAGE_PIXELS`, 64MP) in addition
  to the existing compressed-upload-size limit, closing a decompression-bomb
  path in `decode_image`.
- Rate limiting now covers `/api/tokens`, `/api/admin/*`, `/api/download/*`,
  and the AstroDex routes (previously only upload/process/stack/preset-apply).
- Removed the dead `DEBUG` setting (never read anywhere; misleadingly implied
  a debug mode that didn't exist).
- `pip-audit` and `npm audit --audit-level=high` run in CI; a Trivy scan runs
  against every published image. See `SECURITY.md` for the full policy.

### Known gaps

- Nothing is tagged yet; no published Docker images or GitHub release. *(Resolved
  in 0.2.0: `v0.2.0` is tagged and images are published to `ghcr.io` and Docker
  Hub. Current open items are tracked under `[Unreleased]` above.)*
- `depthShiftIntensity` (a `ProcessingParameters` field with its own slider) is
  dead: nothing in the enhancement pipeline or `depth_shift.py` reads it. The
  actual Depth Shift viewer has its own separate intensity state
  (`useDepthShift`). Found while adding parameter tooltips; not fixed since it
  needs a product decision (most likely: wire it as that viewer's starting
  value), not a copy change. *(Still open.)*

