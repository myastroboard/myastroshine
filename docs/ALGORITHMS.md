# Processing algorithms

Reference for the image processing pipeline. Implementations live in
`app/services/image_processing.py`, `app/services/star_detection.py`,
`app/services/depth_map.py`, and the stacking services. All functions operate on
BGR `uint8` numpy arrays unless noted.

## Contents

- [Upload ingest: FITS / RAW / 16-bit](#upload-ingest-fits--raw--16-bit)
- [Single-image pipeline](#single-image-pipeline)
- [Star removal (starless)](#star-removal-starless)
- [Auto Astro (one-click adaptive enhancement)](#auto-astro-one-click-adaptive-enhancement)
- [Depth map (v1, gradient-based)](#depth-map-v1-gradient-based)
- [Stacking](#stacking)
- [Performance notes](#performance-notes)

## Upload ingest: FITS / RAW / 16-bit

**Linear stack data - FITS (any bit depth) and 16-bit PNG/TIFF - opens as a
composite session**, not through `decode_image`. `POST /api/upload` routes it to
`app/services/linear_upload.py`: the frame is ingested to linear `float32`
(`app/utils/linear_ingest.py` - CFA mosaics debayered, a `(3,H,W)`/`(H,W,3)`
cube read as R/G/B planes, mono left 2D), its field-rotation / vignette border
is trimmed (`crop_low_signal_border`, below), and it is stored as `composite.npy`
with a `StackRecord` linking it to the session (`source="single"`). From there it
is byte-for-byte the stacker's own output: the editor's linear "Stack" step -
background extraction, colour calibration, a tunable deep stretch, all
recomputed from the 32-bit data on every render (see "Post-stack" below) - and
the faint signal never gets quantised to 256 levels on the way in. The response
carries `is_stack: true`.

`decode_image` (`app/utils/image_utils.py`) is what remains for **ordinary 8-bit
photos and camera RAW** (and any other `decode_image` caller, e.g. an AstroDex
handoff that hands in a FITS). It produces the BGR `uint8` array the single-image
pipeline works on. The file extension picks the decoder:

- **FITS** (`.fits`/`.fit`/`.fts`, `astropy.io.fits`) - scientific/linear data
  (8/16/32-bit int or float; `BSCALE`/`BZERO` header scaling applied
  transparently by astropy). A raw stacked frame looks almost black without a
  non-linear stretch, so every FITS upload goes through the auto-stretch below
  regardless of its stored dtype. The first HDU with data wins (some FITS
  files keep an empty primary HDU and put the image in an extension). 2D data
  is treated as monochrome (gray-replicated to BGR) - there's no reliable
  standard header keyword for a Bayer pattern, and guessing one risks a
  garish checkerboard artifact instead of a real debayer, so a raw one-shot-
  colour sensor frame is out of scope here. A `(3, H, W)` or `(H, W, 3)` cube
  is read as R/G/B planes and stretched with one shared, colour-preserving
  transform (`stretch_composite_linear`) at a deep sky target - not three
  independent per-channel stretches.
- **Camera RAW** (`.cr2`/`.cr3`/`.nef`/`.arw`/`.dng`/`.orf`/`.rw2`/`.pef`/`.raf`,
  `rawpy`/libraw) - demosaiced with the camera's as-shot white balance and
  libraw's default sRGB-ish tone response (`use_camera_wb=True`,
  `output_bps=8`). Unlike FITS, this isn't scientific linear data by
  convention - the goal is the same as opening a RAW in any other photo tool:
  a normally-exposed starting point to edit further with this app's own
  sliders, not a from-scratch stretch.
- **Everything else** (including no/unrecognised extension) goes through
  OpenCV, which sniffs the real format from the bytes. Decoded via
  `cv2.IMREAD_UNCHANGED` (not the old `IMREAD_COLOR`, which silently
  truncated any 16-bit source to 8-bit before this) - grayscale sources are
  replicated to BGR, a 4th (alpha) channel is dropped, matching the prior
  behaviour for ordinary 8-bit images exactly. A 16-bit source that reaches
  here (a linear stack that skipped the composite route above, or a
  `decode_image` caller other than `/upload`) still gets the auto-stretch
  rather than a naive `>> 8` bit-shift.

**Auto-stretch** (`_auto_stretch_to_uint8`) is the same "screen transfer
function" auto-stretch used across astro tools (PixInsight's AutoSTF, Siril,
...), applied per plane. A mono FITS uses it directly; a 3-plane cube instead
gets one shared, colour-preserving transform (`stretch_composite_linear`, the
stacked-composite core) so the channels are not rebalanced against each other:

1. Percentile-clip to [0.1, 99.9] and normalize to 0-1 - guards against hot
   pixels/cosmic ray hits setting the black or white point off a single
   outlier pixel (the same small-fraction-of-outliers idea as dehaze's
   atmospheric-light estimate elsewhere in this doc).
2. Shadow (black) point = median - 2.8 * (MAD * 1.4826) (a robust,
   noise-based clip - 1.4826 scales median-absolute-deviation to a
   Gaussian-equivalent standard deviation), re-normalized to 0-1.
3. Solve for the midtones-transfer-function balance `m` that maps the new
   median (the background level) to 0.25, then apply
   `MTF(x; m) = ((m-1)x) / ((2m-1)x - m)` - a rational curve through
   `(0,0)`, `(m, 0.5)`, `(1,1)` - to every pixel. This is what actually
   reveals faint nebulosity/background stars instead of a flat near-black
   frame: a linear capture's real signal usually sits in the bottom few
   percent of the range, and MTF pulls it out non-linearly without blowing
   out the already-bright stars the percentile clip preserved headroom for.

Known limitation: if a 16-bit TIFF/PNG is already a *finished*, non-linear
export (not a linear stack), the composite route's deep stretch will
over-brighten it - export finished work as 8-bit instead, or pull the "Stretch"
control down and turn colour calibration off in the editor's Stack step.

## Single-image pipeline

Applied in this order to minimize artifacts (`apply_parameters`):

0. **Geometry** (`geometry`) - quarter turns (clockwise), then flips, then
   straighten (`cv2.getRotationMatrix2D` + `warpAffine`, scaled up by
   `max((w·cos+h·sin)/w, (w·sin+h·cos)/h)` so the frame stays full), then the
   crop rectangle. Runs first; it changes the working dimensions.
1. **White balance** (`temperature`, `tint`) - per-channel gain in linear RGB;
   6500K is neutral. Warm shifts reduce blue, cool shifts boost blue.
2. **Vignette** (`vignette_correction`, -100..100) - a generic radial gain
   model (not a per-lens calibrated profile), `gain = 1 + (amount/100) *
   dist^2 * 0.8` where `dist` is the normalized distance from centre (0 at
   centre, 1 at the corners). `+100` lifts the corners by 80% (counteracts lens
   vignetting), `-100` drops them to 20% (deepen a vignette for effect, or tame
   an over-corrected stack). Purely geometric - depends on position, not image
   content - so the gain map is computed on a small downscaled grid (128px) and
   resized up; full-resolution precision would be wasted work for a smooth
   analytic function.
3. **Gradient reduction** (`gradient_reduction`, 0-100) - flattens smooth
   background gradients (light pollution, sky glow). A very large Gaussian
   blur approximates the background; genuine DSO structure is
   higher-frequency and survives mostly in the residual, so subtracting the
   blur's own deviation from its mean flattens the background without eating
   into real detail. Estimated on a small downscaled copy (256px) then
   resized back up - a huge blur at full resolution is computationally
   infeasible (an 8000px-wide frame would need a ~5000px-wide kernel to reach
   the same effective sigma), and a smooth low-frequency estimate doesn't
   lose anything by downscaling first.
4. **Dehaze** (`dehaze`, 0-100) - dark-channel-prior haze removal, restoring
   contrast/colour lost to a veiling glow (thin cloud, humidity,
   light-pollution haze). Distinct from gradient reduction's smooth
   *background level* correction: this estimates a per-pixel transmission map
   (`1 - amount * dark_channel(normalized_image)`, dark channel = per-pixel
   min-over-channels then a 15x15 min-filter/erosion) and divides it back
   out, `recovered = (img - atmospheric_light) / transmission +
   atmospheric_light`. Atmospheric light is the brightest 0.1% of dark-channel
   pixels (floored at 0.2 so a very dark frame can't push it near zero).
   Simplified from He et al.'s original - no guided-filter transmission
   refinement, the patch-erosion step already gives a reasonable, if
   blockier, map without a new dependency. The dark-channel/transmission
   estimation (two large-kernel erosions - the expensive part) runs on a
   downscaled copy (800px); only the final per-pixel recovery formula runs at
   full resolution, using the transmission map resized back up.
5. **Contrast** (`contrast`, 0.5-3.0) - linear scaling around the image mean,
   `y = (x - mean) * contrast + mean`, then a mild gamma for a smooth response.
6. **Exposure** (`exposure`, -1..1) - pixel offset, `beta = exposure * 50`.
7. **Highlights / shadows** (-1..1) - masked tone curves; `gray^2` emphasizes
   bright regions, `(1 - gray)^2` emphasizes dark regions, scaled by 0.3.
8. **Whites / blacks** (`whites` / `blacks`, -1..1) - the same masked-tone-curve
   shape as highlights/shadows, but narrower and more aggressive (`gray^4` /
   `(1-gray)^4` weighting, scaled by 0.4) so only the true near-white/near-black
   tail moves, not the broader upper/lower-mid range - the usual distinction
   between "Highlights"/"Shadows" and "Whites"/"Blacks" in most photo editors.
   `x**4` is computed as `square(square(x))`, not `power(x, 4)` - the repeated-
   squaring path is measurably faster at 24MP.
9. **Tone curve** (`curve_points`, empty by default = identity) - a 256-entry
   lookup table (`app/utils/math_utils.py:curve_points_to_lut`), applied via
   `cv2.LUT` identically on each BGR channel (a combined RGB curve - see
   "Colour curves" below for independent per-channel curves). Points are
   `(input, output)` 8-bit level
   pairs spanning the full 0-255 range (`ProcessingParameters` validates: at
   least 2, first at x=0, last at x=255, strictly increasing x); between them
   the curve is a **monotone cubic Hermite spline** (Fritsch-Carlson tangent
   correction), not a plain polyline - a handful of dragged points make a
   smooth curve instead of visible straight-line kinks, and the correction
   guarantees the spline never overshoots past a control point's value in the
   segments next to it (an overshoot would locally crush shadows or blow out
   highlights the user never asked for). A user-drawn curve subsumes and can
   replace manual contrast/exposure/highlights/shadows tweaking, but doesn't
   replace those sliders - both stages run, in this order, so a curve is a
   fine-tuning layer on top of the basic tone controls, matching how most
   photo editors separate "Basic" tone sliders from a "Curve" panel.
10. **Colour curves** (`red_curve_points` / `green_curve_points` /
   `blue_curve_points`, each empty by default = identity) - the same
   `curve_points_to_lut` LUT/spline as the master tone curve above, but one
   independent curve per channel (`cv2.split`, `cv2.LUT` per channel,
   `cv2.merge`) instead of one curve applied identically to all three. For
   colour grading, or a colour cast a single white-balance gain can't reach
   at just one tonal range (e.g. a slightly green background sky only in the
   midtones - white balance is one multiplicative gain per channel, uniform
   across the whole tonal range, so it can't fix a cast that only shows up
   at one brightness level). Runs immediately after the master curve, so it's
   a further fine-tuning layer on top of it, same relationship the master
   curve has with the basic tone sliders. Any of the three left empty is
   skipped independently - a red-only edit never touches green/blue.
11. **Saturation** (0-2) - scale the HSV S channel.
12. **Vibrance** (0-2) - saturation boost weighted by `(1 - current_saturation)`
   so already-saturated pixels move less.
13. **Clarity** (-1..1) - unsharp mask against a Gaussian blur with
   `sigmaX=9` (`cv2.GaussianBlur` auto-selects an odd kernel from sigma,
   around the high-20px range here); positive sharpens, negative softens.
14. **Denoise** (0-100) - bilateral filter; map to diameter 5-20 and
   sigma_color / sigma_space 75-150. Above 50, add a 3x3 morphological close.
   With `denoise_engine = "deepsnr"` this stage instead runs the DeepSNR model
   **early**, right after the sky/optics corrections (see "Quality path" below);
   the classical filter here becomes a no-op and the 0-100 value blends DeepSNR's
   output back.
15. **Chroma denoise** (`chroma_denoise`, 0-100) - the same bilateral filter as
   Denoise, applied only to the Cr/Cb channels (`COLOR_BGR2YCrCb`), leaving
   luma untouched. Colour speckle is usually more objectionable than luma
   noise in a stacked astro frame, and can be smoothed much harder than luma
   without an apparent loss of detail, since detail lives almost entirely in
   luma.
16. **Star reduction** (`star_reduction` 0-100, `star_sensitivity` /
   `star_max_size` 0-100) - shrink *individually detected* stars, leaving
   everything else untouched. Detection (`StarDetectionService.detect`, shared
   with the `POST /api/star-mask/{id}` mask-preview endpoint) isolates compact
   bright features with the same 9x9-ellipse white top-hat as before
   (nebulosity varies too slowly to register), thresholds it, and finds each
   star as one connected bright region (`cv2.connectedComponentsWithStats`);
   its equivalent radius comes from the region's pixel area
   (`sqrt(area / pi)`). `star_sensitivity` maps inversely to that threshold
   (higher sensitivity -> lower threshold -> fainter/smaller points register);
   `star_max_size` caps the equivalent radius counted as a star, so bright
   diffuse cores (galaxy nuclei, nebula knots) aren't shrunk as if they were
   one. A small pre-blur (`sigma=0.8`), a minimum region area (2px), and an
   absolute top-hat floor (12, in raw 0-255 units, on top of the relative
   threshold above) keep ordinary sensor/JPEG noise from registering as
   hundreds of fake stars - the relative threshold alone degenerates on a
   frame with no real point source at all, since a fraction of a small,
   noisy peak is itself a tiny absolute value. Runs at native resolution - an
   earlier version used
   `skimage.feature.blob_dog` on a downscaled copy to stay inside the
   performance budget, but the downscale's anti-aliasing routinely erased
   small/faint stars before detection ever saw them (a busy real star field
   visibly under-caught); connected components is a single near-linear pass,
   cheap enough at full 24MP resolution that no downscale is needed. For each
   detected star, a soft-edged circle (radius `1.6x` the detected radius,
   Gaussian-feathered) is drawn into a mask *local to that star*; the old
   implementation built one image-wide mask from the raw top-hat, which is
   what let it drag down nearby nebulosity and leave halos. The mask is
   scaled by `0.4 + 0.6 * amount`, and inside it the image is blended toward
   an eroded (1-4 iterations of a 3x3 ellipse), `1 - 0.6 * amount` darkened
   copy of itself - erosion genuinely shrinks the bright disc while keeping
   the star's own colour and local texture. That fill is floored, per pixel,
   at `StarDetectionService.local_background` (a morphological opening -
   erosion then dilation - with a kernel sized to the current `max_size`, so
   it fully removes even the largest star this call can return): the eroded
   value can never drop below what the real surrounding sky/nebulosity
   actually looks like there, so a small isolated star can't be crushed to a
   black dot the way plain erosion+darkening could. A version in between
   tried blending toward a `cv2.inpaint` (Telea) reconstruction instead
   (reasoning: it can never go below the real background either); in
   practice that produced oversized, flat, textureless pale discs on a real
   photo - worse than the black-dot bug it was meant to fix - because
   inpainting fills from the mask boundary rather than shrinking the star's
   own disc in place.
17. **Sharpness** (0-2) - below 1.0 Gaussian blur, above 1.0 Laplacian-kernel
    sharpen blended by `(sharpness - 1) * 0.5`.

Preview path downscales to 512 px (`preview_max_size`) for instant feedback; the
full-resolution result is computed on demand or via the job queue.

**Star removal splits this list.** When `star_removal > 0` (see "Star removal
(starless)" below), stages 0-4 (geometry + the sky/optics corrections) run on
the whole frame, then the stars are pulled out, stages 5-17 run on the
*starless* image, and a final `star_recombine` step screen-blends the stars
back. `star_removal = 0` (the default) runs the flat list above unchanged.

## Star removal (starless)

`StarlessService` (`app/services/starless.py`) - the classic deep-sky workflow:
separate the stars from the nebulosity so the starless image can be stretched /
sharpened / denoised hard without bloating the stars, then blend the stars back.
Driven by two parameters, `star_removal` and `star_recombine` (0-100 each, both
default 0 = off); detection reuses `star_sensitivity` / `star_max_size`.
`star_removal_engine` selects the split backend - the classical one below, or an
operator-installed StarNet2 (see "Quality path" at the end of this section).

**Split** (`StarlessService.split`):
1. Detect stars with `StarDetectionService.detect` (the same per-star detector
   star reduction and the mask-preview endpoint use), at native resolution.
2. Build the starless *estimate* - what the nebulosity looks like with the stars
   gone - with **two passes of a median blur** on a downscaled copy (~520 px),
   the window sized past `star_max_size` (so features larger than the biggest
   allowed star - a galaxy core, a bright nebula knot - survive as they should).
   A median window rejects a star as an outlier even where stars crowd a big
   fraction of it, so it holds up on a dense Milky Way field; a morphological
   opening / geodesic reconstruction was tried first and left a blotchy mesh of
   star-blob remnants there, and a `cv2.inpaint` fill (tried before that) left
   dark halo rings around the brighter stars because it fills from the mask
   boundary. The estimate is deliberately smooth and low-frequency - it only
   ever fills the feathered star mask, where there is no real signal to
   preserve.
3. Draw each detected star into a mask as a circle `3x` its measured radius
   (min 4 px) - generous, because the estimate under the mask *is* the
   surrounding nebula continued inward, so an oversized mask only softens the
   nebula slightly there, whereas an undersized one leaves a bright core and a
   dark ring. Then grow the mask wherever the image still sits well above the
   estimate *right next to* an already-masked star (a bright star bloated past
   its detected radius, or its glow) - bounded to a ~10 px neighbourhood of the
   detected stars, so an undetected faint star or a small nebula knot elsewhere
   is left to the sensitivity control. Gaussian-feather (`sigma=2.5`).
4. `starless = lerp(image, estimate, star_removal/100)` within the feathered
   mask - a lower value thins the field rather than clearing it.
5. `stars_layer = clip(image - starless, 0, 255)` - the removed star flux, on
   black.

**Recombine** (`StarlessService.recombine`): screen-blend
`stars_layer * (star_recombine/100)` onto the processed starless image
(`255 - (255-base)(255-stars)/255`). Screen, not a plain add, because starlight
is additive but must not clip the nebulosity it lands on. The stars were pulled
*before* the contrast/curve stretch, so they come back tighter and a touch
dimmer than a normal edit leaves them - that is the point of working starless;
`star_recombine = 100` is a straight restore.

**Split point** (after `dehaze`, before `contrast`): geometry, white balance,
vignette correction, gradient reduction and dehaze are corrections to the sky
and the optics - they belong on the whole frame, stars included - so they run
before the split. Everything creative runs on the starless image. `star_reduction`
keeps its slot in the creative stages and is a natural no-op once the stars are
gone.

**Known ceiling** (confirmed on real photos - NGC 281, the Pelican, M31, M74,
IC 342, NGC 7000, the Bubble): a nebula or galaxy over a normal star field comes
out clean - structure and cores preserved, small/medium stars gone with no ring.
The limits: (a) a frame's few brightest, near-saturated stars survive as a small
core or a faint coloured halo (the white centre goes, the outer glow doesn't);
(b) faint stars below the sensitivity threshold stay; (c) a **dense Milky Way
star field** (thousands of overlapping faint stars, e.g. the Cassiopeia region
around the Bubble) leaves a soft mottled texture where it was - there is no real
"between the stars" for the estimate to reconstruct. Classical removal fills
from the neighbourhood and has no model of what a star sits on top of; this is
exactly where a trained model wins, and why the optional StarNet2 engine (below)
exists.

**Quality path - StarNet2 / DeepSNR as optional external engines.** The roadmap
paired the classical path with "an ONNX StarNet-style model (quality path)".
Bundling a model was ruled out on licensing (the canonical `nekitmm/starnet`
weights are CC BY-NC-SA, and the `starnetastro.com` builds are not
redistributable). Instead the operator installs the tool themselves and
MyAstroShine shells out to it - arm's-length, never bundled. Setup and licensing:
`docs/DEPLOYMENT.md` "External ML engines" and `THIRD_PARTY.md`.

`star_removal_engine` (`"classic"` / `"starnet2"`) and `denoise_engine`
(`"classic"` / `"deepsnr"`) pick the backend per edit; the ML choice is honoured
only when the matching `AppSettings` path points at a working binary (probed by
`app.services.engine_probe`), and any failure - missing binary, non-zero exit,
timeout, bad output - logs and falls back to the classical code.

- The shared machinery is `app.services.external_engine`: `run_cli` writes a
  TIFF, runs `<tool> -i … -o … -q [-s stride] --machine-progress`, reads the
  result back (BGR round-trips through `cv2` unchanged); `ModelEstimateCache`
  stores the output per session, keyed on the pixels fed to the stage plus the
  engine settings (the editor re-runs the pipeline on every slider move, so an
  edit that doesn't touch those must reuse the estimate).
- **StarNet2** (`external_starless`): `apply_parameters` takes a `starless_split`
  override at the existing split point; `blend_starless` applies `star_removal`
  exactly as the classical split, and the recombine step is unchanged.
- **DeepSNR** (`external_denoise`): `apply_parameters` takes a `denoise_stage`
  override that runs **right after the background corrections**, before any tone
  work - a NAFNet restoration model wants linear-ish data, and keying the cache
  on the pre-stretch image means creative edits don't re-invoke it. The classical
  `denoise` creative stage is dropped when this is active; `blend_denoise`
  applies the 0-100 strength.
- A pass is seconds to minutes, so it streams. Both tools emit `--machine-progress`
  JSON Lines on **stderr**
  (`{"schema":"starnetastro.cli.progress.v1","event":"progress",…,"percent":P}`,
  `P` 0-100); `_run_streaming` reads them off a merged pipe, `_parse_progress`
  pulls `percent`, and each is forwarded to the job's `on_step` across a band
  (`_DEEPSNR_PROGRESS_BAND` 12-40, `_STARNET2_PROGRESS_BAND` 20-80); job progress
  is made monotonic so later stages can't pull the bar back.
- No new Python dependency: each CLI is self-contained (its own ONNX Runtime).
  Verified against StarNet2 2.6.1 / DeepSNR 1.3.1 (linux-x64) on the Debian-13 image.

## Auto Astro (one-click adaptive enhancement)

`AutoAstroService.suggest_parameters(image)` (`app/services/auto_astro.py`)
analyses the session's original image and proposes a `ProcessingParameters`
set - deliberately scoped to what histogram/black-point/star-density can
drive with confidence; everything else stays at its default.

**Tone stretch** (grayscale luminance percentiles, robust to a few hot/cold
pixels) is deliberately not a single uniform curve: the goal is *separation*
between the background and the DSO, not just filling the tonal range evenly.
- `bp = percentile(gray, 0.5)`, `wp = percentile(gray, 99.5)`. If
  `wp - bp < 10` (a flat/degenerate frame), tone changes are skipped entirely.
- `contrast = clip(210 / (wp - bp), 0.5, 3.0)` - stretch the real signal range
  toward filling most (not all - headroom) of 0-255.
- `exposure` is chosen so the black point, after `apply_contrast`'s own
  mean-centered formula (`y = (x-mean)*contrast + mean`), settles near a
  near-black floor (~3) - a crushed background reads as depth, so this isn't
  protected from crushing the way an early version did (floor ~8, which read
  as flat/washed-out against a real photo).
- `highlights` is **never positive** - only pulled back (`clip(-clipped_fraction
  * 8.0, -1.0, 0.0)`) when a meaningful fraction of pixels already clip near
  white (`>= 250`), otherwise 0. An earlier version also boosted highlights
  (`+0.2`) to lift the DSO's own bright detail, but this pipeline runs
  `star_reduction` *after* highlights/contrast (see `apply_parameters`), so
  boosting brightness here blew stars out toward flat, saturated plateaus
  before the shrink step ever saw them - erosion can't meaningfully shrink a
  plateau with no gradient left to eat into. A DSO's own brightness comes from
  the contrast stretch above, not from this.
- `shadows = -0.35` (deepens the background) unless the frame is already
  mostly near-black (`<= 5`) beyond what a typical deep-sky background
  accounts for, in which case further crushing would just eat real faint
  signal. `apply_highlights_shadows` weights `shadows` toward the *darkest*
  pixels only (`shadow_mask = (1 - gray)^2`), so this mostly darkens the empty
  sky and barely touches the DSO itself - exactly the "highlight the object,
  darken the background" separation real deep-sky processing aims for, rather
  than one flat exposure shift.
- All four values are rounded to 2 decimals before being returned - the raw
  percentile-derived floats carry a dozen digits of spurious precision that
  read as broken in the slider UI.

**Star density** (reuses `StarDetectionService.detect` at its default
`sensitivity=50, max_size=30`): `star_reduction = clip(round(5 *
log1p(density)), 0, 50)`, where `density` is detected star count per
megapixel. Log-scaled rather than linear: real star fields span orders of
magnitude in density (tens/MP for a single short frame, 1000+/MP for a deep
stack), and a linear mapping saturates at the cap for almost any real busy
field, defeating "gentle starting point" - a first version (`density * 0.8`)
hit its cap of 60 on a real ~1000/MP deep-stack photo just as readily as on a
merely-busy one. Capped at 50 (not 100) regardless - Auto Astro is meant as a
starting point, not a maxed-out edit.

**A note on very bright stars**: any meaningful contrast stretch pushes
already-bright pixels further toward clipping, including a photo's brightest
stars - by the time `star_reduction` runs (after `contrast`/`highlights`/
`shadows`, see the pipeline order above), a star that was already near-white
in the original can be a wide, flat, saturated plateau with little gradient
left for erosion to shrink into. This reads as a small round white disc even
after reduction - expected for a frame's few brightest "anchor" stars (real
astro-processing tools leave these visible after reduction too), not a defect
in the shrink algorithm itself. Actually removing a star regardless of
brightness is the separate, more aggressive "Star removal (starless)" operation
above (`star_removal` / `star_recombine`), not reduction.

## Depth map (v1, gradient-based)

`estimate_depth(image)` returns a single-channel `uint8` map, `0 = far`,
`255 = near`:

1. Grayscale, then Sobel gradients (`ksize=5`) in x and y.
2. Gradient magnitude `sqrt(gx^2 + gy^2)`, min-max normalized to 0-1, scaled to
   0-255. High-detail regions (stars, structure) are near; smooth sky is far -
   the map is **not** inverted.
3. Morphological close (5x5 ellipse) + 21x21 Gaussian blur for smoothness.

`generate_parallax_layers(image, depth_map, num_layers=7)` slices the 0-255 depth
range into `num_layers` equal bands, builds a dilated `inRange` mask per band,
and emits BGRA layers (alpha = mask) ordered far (index 0) to near. The map and
layers are cached under `{storage}/{session_id}/depth/`.

`depth_statistics(depth_map)` reports min/max/mean/median and the percent of
pixels above 200 (`bright_areas_percent`).

**ML backend - evaluated, not adopted (2026-09-05).** Tested both MiDaS Small
(`model-small.onnx`, 66MB, ONNX Runtime, 13ms/frame) and `Intel/dpt-hybrid-midas`
(ViT-hybrid, ~490MB, ~0.7s/frame on CPU) on a real single-exposure test photo
(NGC 281): both produced a near-featureless smooth gradient with no star or
nebula structure (Laplacian std of the normalized depth map: MiDaS Small 0.82,
DPT-Hybrid 0.82 - essentially identical despite DPT-Hybrid being ~7x larger),
versus 1.60 for the gradient method above, which clearly resolves individual
stars. Both integrations were verified correct first on a synthetic scene with
real depth cues (sharp foreground vs. blurred background), where they behave
as expected - the gap is specific to starfield content, not a bug. Root cause:
both models are trained on natural-photo depth cues (defocus blur increasing
with distance, perspective, occlusion) that a single deep-sky exposure simply
doesn't contain, and a larger network can't recover cues that aren't in the
pixels. No ML dependency added; the gradient method above stays the only depth
backend.

### Focal point

`estimate_depth(image, focus_point=None)` - with no `focus_point`, identical
to the above. With one (normalised `x`/`y`, 0-1), a radial field centred on
it is blended into the gradient-normalized depth *before* step 3
(`gradient_depth = (1-w)*gradient_depth + w*radial`, `w=0.5`): for each pixel,
`radial = 1 - clip(distance_from_focus_point / (image_diagonal/2), 0, 1)` - 1
at the chosen point, 0 at the frame's far corners. This is what makes the
picked point read as "near" in the parallax, not just whatever happens to be
detailed. `w=0.5` is a first-pass constant, like other heuristics this
session, to revisit if real testing shows the centering too strong/weak.

## Stacking

The stacking pipeline works entirely in linear `float32` data. (An earlier
v1.1 attempt - ORB/SIFT homography on stretched 8-bit frames, MAD "cosmic ray"
masking, uint8 combination - was never run on real data and produced a
near-black composite on a real Seestar set; it was replaced wholesale.) The
current pipeline was validated against Siril / DeepSkyStacker / APP / WBPP on
real sets.

### Linear ingest (`app/utils/linear_ingest.py`)

`ingest_frame(bytes, filename)` -> `LinearFrame`: `float32` pixel data in a
nominal `[0, 1]` range, linear (no screen stretch), CFA mosaic kept intact.

- **FITS** - `BZERO`/`BSCALE` applied by astropy, divided by the dtype full
  range. A `BAYERPAT` header marks the frame CFA and the 2D data stays a
  mosaic; acquisition keywords (`EXPTIME`, `GAIN`, `CCD-TEMP`, ...) are kept in
  `metadata`. `(3, H, W)` / `(H, W, 3)` cubes read as R/G/B planes.
  `ROWORDER = BOTTOM-UP` is flipped.
- **Camera RAW** - `rawpy` linear postprocess (`gamma=(1, 1)`,
  `no_auto_bright=True`, 16-bit, camera WB). Debayered by libraw.
- **Everything else** via OpenCV. 16-bit is scaled to `[0, 1]` as linear; 8-bit
  is a low-precision, already-stretched preview - flagged `already_stretched`
  and passed through an approximate sRGB EOTF.

`to_display_bgr(frame)` auto-stretches a frame to a BGR thumbnail (CFA gets a
2x2 superpixel de-mosaic). Two debayer paths feed the pipeline:
`superpixel_rgb(frame)` (2x2 superpixel, half-res, no colour fringing) for the
registration measurement pass, and `debayer_rgb(frame)` - OpenCV's **edge-aware**
demosaic (`COLOR_BayerXX2RGB_EA`, full resolution, mapped through 16-bit since
OpenCV does not demosaic float) - for the align/combine passes. A
`ROWORDER = BOTTOM-UP` flip on an even-height mosaic also swaps the Bayer rows so
the pattern stays correct.

Uploaded frames are stored at their **source bit depth** - a 16-bit camera frame
round-trips through `uint16` (`round(x * 65535)`) losslessly at half the size of
a float32 `.npy`; a float FITS keeps float32. They are kept `stacking_retention_hours`
(default 12) - long enough to re-stack; the composite a run produces is a normal
session and lives the full session lifetime.

### Calibration (`app/services/calibration.py`)

Master dark / flat / bias / dark-flat frames, when uploaded, are stacked into
masters (**per-pixel median** - standard for calibration, robust to a transient
in one sub) and cached on disk keyed on the source frame count. Each light frame
is calibrated **on the CFA mosaic, before debayer**:

    calibrated = (light - bias - dark) / flat_field

- the dark is scaled by the exposure ratio when a separate bias master isolates
  its thermal component (`dark_current = dark - bias`);
- `flat_field` is the master flat with its own dark (or the bias) removed,
  normalised to a mean of 1, and floored at 0.05 so a dead corner cannot blow a
  pixel up;
- a **bad-pixel map** flags hot pixels (master dark, > 8 robust sigma above the
  per-Bayer-phase median) and dead/occluded pixels (master flat, > 8 sigma
  below); with `cosmetic_correction` each flagged pixel is replaced by the 3x3
  median of its own Bayer phase. This is the honest replacement for the removed
  "cosmic ray" MAD mask.

### Frame quality (`app/services/frame_quality.py`)

Every frame the registration pass measures is scored: `score_frames` normalises
star count, star **FWHM** (`2 x` the median detected-star radius) and
**roundness** (`min(w, h) / max(w, h)` of each star's bounding box), sky
background and background noise against the stack's own medians, and produces:

- a **score** 0-100 (mostly SNR, then star count, sharpness, roundness) for the
  UI;
- the `weighting = "quality"` integration weight: `SNR^2` tempered by star count
  and sharpness, each clamped to 0.25-4x and normalised to a median of 1;
- an **accept / reject** verdict when `quality_filter` is not `off`. Thresholds
  scale with the level (`lenient` / `moderate` / `strict`) and are all relative
  to the median: `star_count < f x median` -> `clouds`, `fwhm > k x median` ->
  `soft`, `roundness < r` -> `trailed`, `background > median + s x MAD` ->
  `bright_sky`. Below four frames nothing is judged (the medians are too shaky).

Rejected frames are dropped before the reference pick and the combine, and
counted in `frames_auto_rejected`. The user overrides per frame: unchecking a
frame adds it to `included_frames` (protected from the filter on the next run),
checking it drops that protection.

### Registration (`app/services/star_match.py`)

`StarMatchService.align(source_centroids, target_centroids, transform)` aligns
two star fields by **asterism (triangle) matching**, vendored in the style of
`astroalign` (no scipy / `sep` / `scikit-image`):

1. For each of the ~60 brightest stars in each frame, build triangles from its
   nearest neighbours and describe each by `(mid_side / long_side,
   short_side / long_side)` - invariant to translation, rotation and scale.
2. Match each source triangle to its closest target descriptor; the ordered
   vertices give candidate point correspondences.
3. `cv2.estimateAffinePartial2D` (`similarity`) or `cv2.estimateAffine2D`
   (`affine`) with RANSAC fits the transform; it is rejected if there are too
   few inliers, the inlier RMS is over 2 px, or the scale is not within 0.5-2x.
   `translation` keeps only the median inlier shift.

### Integration (`app/services/integration.py`)

`IntegrationService.integrate` runs three memory-bounded passes so a
thousand-frame stack fits in bounded RAM (only a few frames and one row-tile
ever resident):

1. **Register** - calibrate then superpixel-debayer each frame (half resolution
   is plenty for centroids), detect stars (`StarDetectionService`), measure
   background / 95th-percentile scale / high-pass noise / FWHM / roundness, and
   **score** the frames (see Frame quality above) - the ones the `quality_filter`
   rejects are dropped here. The best-scored remaining frame is the
   **reference**; every other kept frame is asterism-matched to it. Frames that
   fail to match are dropped and counted in `frames_excluded`.
2. **Align** - reload each kept frame, calibrate it and **interpolating**-debayer
   it at full resolution, warp it into the reference frame (`cv2.INTER_LANCZOS4`,
   NaN outside the frame footprint - the transform's translation scaled up from
   the half-res registration), normalise it (`x' = m*x + a` where
   `m = scale_ref / scale_frame` clamped to 0.2-5x and `a` matches the
   backgrounds), and stream it to a `float16` memmap on disk. The combine tile
   size adapts to the frame count to keep the working set bounded.
3. **Combine** - tile over the memmap rows. Per pixel across the stack:
   **iterative sigma-clip around the mean** (2 iterations, k=3 - fast, sum-based;
   `np.nanmedian` on the stack axis is ~100x slower), then `winsorized_sigma`
   clamps the outliers (count preserved) or `sigma` drops them, then a
   **weighted mean** (`none` = equal / `noise` = `1/noise^2` clamped 0.25-4x /
   `quality` = the frame-quality score's combined weight). Rejection is skipped
   where fewer than 30% of frames cover a pixel (the field-rotation
   wedge - the per-pixel sigma there is unreliable). `median` combination uses a
   true `nanmedian` (slower, opt-in).

The reference is **not** simply the frame with the most stars: on an alt-az
mount that is often an outlier pointing or a transparency spike, and aligning
to it shrinks the common footprint and off-centres the target. `_pick_reference`
picks the frame nearest the **session's temporal middle** (which halves the
field rotation to either end) with a typical star count and good sharpness.

Each pass runs on a **thread pool** (`_map_frames`, auto-sized to the CPU count
and capped at 4, `stacking_workers` to tune). Threads not processes - a Celery
prefork worker is daemonic - which is fine because the per-frame hot path
(decode, calibrate, `warpAffine`, connected components) and the combine's
`partition` / `clip` / reduce are all GIL-releasing C. Progress carries a
`"340/1066"` frame counter.

After the align pass a **checkpoint** (`accum/plan.json` + the aligned memmap)
is written and dropped only on success, so a run killed during the combine - or
a re-stack that changes only the combination / rejection / weighting / drizzle
(the checkpoint signature ignores those) - resumes from the aligned frames. The
stale-work sweep reclaims an abandoned checkpoint's ~13 GB memmap after 30 min.

### Drizzle (`app/services/drizzle.py`, opt-in `drizzle_factor` 2-3)

Variable-pixel linear reconstruction (Fruchter & Hook 2002), run as a fourth
pass **after** the normal align + combine. `_reference_stats` gives a 1x
per-pixel median + robust sigma from the aligned memmap; `_drizzle` then decodes
each kept frame again, normalises it, masks pixels that deviate more than
`_KAPPA` sigma from that median (cosmics / hot pixels / a satellite streak), and
"drops" each surviving input pixel - a square of side `_PIXFRAC` (0.7, < 1
sharpens) mapped through the frame's registration transform - onto the `scale`x
output grid, its flux area-distributed over the nearest 2x2 output cells. The
drop can spill past that 2x2, but the missing area is lost from `flux` *and*
`weight`, so `flux / weight` (the final composite) stays unbiased. It correlates
neighbouring-pixel noise and adds ~1 s/frame, so it is off by default; the
Seestar's alt-az field rotation supplies the sub-pixel dither it needs.

### Post-stack: wedge crop, then the non-destructive editor pre-stage (`app/services/post_stack.py`)

The post-stack work splits by *when* it runs.

**`apply_post_stack`** runs once, in `StackingService`, and only **crops the
rotation wedge** - `_combine` emits a per-pixel frame-coverage map, and
rows/columns where most pixels were reached by fewer than half the frames are
trimmed (capped at 45% of either axis). That crop defines the canvas, so it is
baked into the saved `composite.npy` (still linear 32-bit, otherwise untouched).

**`crop_low_signal_border`** is the same idea for a *single uploaded stack*
(`app/services/linear_upload.py`), which has no coverage map: a Seestar / alt-az
live stack carries a field-rotation + vignette footprint at the frame edge where
one or more channels collapse well below the interior sky (the "red top / marked
corners" a hard stretch exaggerates - a sharp edge falloff `background_extraction`
can neither model nor fit around). A dead-pixel mask is derived from the pixels
(any channel more than 5 robust sigma below the interior 40th-percentile sky, on
a copy downscaled to <=384 px), then the largest centred rectangle that stays
>=92% live is kept - same logic as the wedge crop, capped at 30% of either axis
and skipped entirely when the trim would be larger (a mis-detection) or smaller
than a few pixels. Also baked into `composite.npy`; the box is recorded in
`quality_report["border_crop"]`.

**`render_stack_base`** runs on every editor render (the "Stack" step, driven by
`ProcessingParameters.stack`), turning the linear composite into the BGR image
the enhancement pipeline works on:

1. **Background extraction** (`background_extraction`, 0-100) - each channel's
   sky is sampled on a 22x22 tile lattice (an 8th-percentile per tile, the sky
   between the stars) **on a copy downscaled to <=640 px**; a degree-2 polynomial
   is fitted, tiles whose residual is over 1.8 robust sigma (plus their
   neighbours) are dropped as objects and it is refitted (3 iterations); the
   fitted surface is cubic-resized back to full resolution and `strength`x of it
   subtracted, flattening toward the darkest real sky. Degree 2 by design - a
   paraboloid can only be a smooth gradient, never a nebula. A **frame-edge-only
   residual correction** is then added on top (`_border_residual`): the
   object-free sky residual to the poly, smoothed and multiplied by a mask that
   is 0 across the interior and ramps to 1 at the frame edge. This bends the
   surface to the sharper edge/corner falloff a paraboloid can't reach (a
   Seestar / alt-az stack's rotation-and-vignette footprint the border crop only
   partly took), while a galaxy halo or a frame-filling nebula in the interior
   stays untouched. Estimating on the downscale keeps this ~100 ms so it can
   re-run per slider move.
2. **Colour calibration** (`color_calibration`, on/off) - the per-channel sky
   level is equalised (neutral grey background), then the channels are scaled so
   their means match, measured on the signal above each channel's own sky level
   so a large shared pedestal (a Seestar/ASIAIR live stack, not bias-subtracted
   like the multi-frame stacker's own composite) can't swamp it (gains clamped
   to 0.5-4x).
3. **Stretch** (`stretch`, 0-1) - the sky is neutralised (subtract each channel's
   low percentile) and **one** MTF stretch, derived from the luminance, is
   applied to all three channels. `stretch` sets the auto-stretch target
   background by log interpolation (0 -> 0.05, 0.5 -> 0.10, 1 -> 0.20), so higher
   pulls up fainter signal at the cost of a brighter, noisier background.

Nothing here touches `composite.npy`; every value recomputes the working image
from the linear data, so the stretch/background/colour choices stay reversible
and never lose highlight or shadow detail to an early 8-bit quantisation. Denoise
and photometric calibration are still the rest of the editor's job.

The composite is saved as 32-bit `composite.npy`; the editor session is seeded
with `render_stack_base` at the `StackParameters()` defaults (so the first
before/after view matches). `quality_report` records the reference frame, the
mean registration RMS, the rejected-sample count, whether calibration ran and
whether the wedge was cropped, and the `frames` table (per-frame metrics +
accept/reject). `snr_improvement` is `sqrt(effective N)` where effective N =
`(sum w)^2 / sum(w^2)`; `measured_noise_reduction` is the reference-frame vs
composite high-pass noise ratio. On a real 100-sub Seestar set: the Bubble
Nebula centred, the wedge cropped, a neutral flat background, ~9x lower noise.

`ImageProcessingService` runs the whole creative pipeline in BGR float32 `[0, 1]`
(quantising only at the encode boundary); the stages that are genuinely
uint8-native - LUT curves, HSV saturation, bilateral denoise, the star detector -
keep a short local round-trip, and each `apply_*` still accepts a uint8 image
directly (converting in and out) for the upload geometry pass and the per-stage
tests.

## Performance notes

| Operation | Typical time (3840x2160) |
|-----------|--------------------------|
| Contrast / exposure / white balance | 5-15 ms |
| Highlights / shadows | 20-30 ms |
| Whites / blacks | ~200-250 ms (measured at 24MP, scaled) |
| Vignette correction | ~90 ms (downscaled gain map) |
| Gradient reduction | ~90 ms (downscaled background estimate) |
| Dehaze | ~200-250 ms (downscaled dark-channel/transmission) |
| Clarity (unsharp) | 30-50 ms |
| Denoise (bilateral) | 100-300 ms |
| Chroma denoise (bilateral, Cr/Cb only) | ~100 ms |
| Depth map (Sobel) | 50-100 ms |
| Stacking, per frame (calibrate + register at half-res + align at full-res debayer + combine) | ~0.4-1 s (three IO passes, run across `stacking_workers` threads) |

Whites/blacks and highlights/shadows cost the same shape of work (a full-res
grayscale conversion + masked blend) but were measured at different times -
if you see one much cheaper than the other, re-measure both rather than
trusting either number blindly.

With `PROCESSING_MODE=queue` the whole pipeline runs on the Celery worker, off
the request path; the editor's 512 px preview keeps slider feedback fast while
the full-resolution render is produced on demand.
