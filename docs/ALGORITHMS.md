# Processing algorithms

Reference for the image processing pipeline. Implementations live in
`app/services/image_processing.py`, `app/services/star_detection.py`,
`app/services/depth_map.py`, `app/services/stretch.py`,
`app/services/color_calibration.py`, `app/utils/starlet.py`, and the stacking
services. The enhancement stages work on BGR `float32` in `[0, 1]` (each also
accepts `uint8`); the Stack step works on the linear composite.

## Contents

- [Upload ingest: FITS / RAW / 16-bit](#upload-ingest-fits--raw--16-bit)
- [Single-image pipeline](#single-image-pipeline)
- [Star removal (starless)](#star-removal-starless)
- [Looks (the "Style" step)](#looks-the-style-step)
- [Auto Astro (one-click adaptive enhancement)](#auto-astro-one-click-adaptive-enhancement)
- [Depth map (v1, gradient-based)](#depth-map-v1-gradient-based)
- [Stacking](#stacking)
- [Performance notes](#performance-notes)

## Upload ingest: FITS / RAW / 16-bit

**Linear stack data - FITS (any bit depth), 16-bit PNG/TIFF, and a linear DNG -
opens as a composite session**, not through `decode_image`. A linear DNG is one
whose image is already demosaiced RGB (`LinearRaw`, libraw's `RawType.Stack`):
an **Apple ProRAW**, which the phone has already merged from a burst and
demosaiced, or a DNG converter's output. Decoding one through the 8-bit RAW path
below threw away the night: libraw's auto-brightening lifted a 10 s night-mode
sky to ~68% grey (the phone's own render keeps it ~36%). When a ProRAW carries
Apple's `semanticskymatte` (a quarter-resolution sky/landscape matte, read with a
minimal TIFF directory walk in `app/utils/sky_mask.py` and rotated to the image's
orientation), it is stored as `sky_mask.npy` and the "Stack" step uses it (see
"Nightscapes" under Post-stack); the border crop is skipped then, since the dark
edge is the landscape, not a dead stack border. `POST /api/upload` routes it to
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
photos and camera RAW** (and any other `decode_image` caller, e.g. an Astrodex
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
  `rawpy`/libraw; a Bayer `.dng` - a linear one takes the composite route above) - demosaiced with the camera's as-shot white balance and
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
   **Green removal** (`green_removal`, 0-100) follows it: SCNR "average
   neutral", `G' = G - amount * max(0, G - (R + B) / 2)`. A one-shot-colour
   sensor's residual green cast goes (almost nothing in the deep sky is green),
   while a teal OIII filament keeps most of its colour because its blue lifts the
   cap.
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
11. **Saturation** (0-2) - each pixel's colour is scaled away from its own
   luminance, `L + (rgb - L) * s` (Rec. 709 weights), in float - brightness is
   kept, and a faint low-chroma nebula is not posterised the way the former
   8-bit HSV round trip quantised it.
12. **Vibrance** (0-2) - the same luminance-anchored boost, weighted by
   `(1 - current_saturation)` (saturation = `(max - min) / max`) so
   already-saturated pixels move less.
13. **Clarity** (-1..1) - unsharp mask against a Gaussian blur with
   `sigmaX=9` (`cv2.GaussianBlur` auto-selects an odd kernel from sigma,
   around the high-20px range here); positive sharpens, negative softens.
14. **Denoise** (0-100) - multiscale wavelet shrinkage of the luma plane
   (`app/utils/starlet.py`). The **starlet** transform (isotropic undecimated
   "a trous" B3-spline - the transform PixInsight's MultiscaleLinearTransform and
   Siril's wavelets use) splits the plane into detail layers of doubling scale
   plus a smooth residual, reconstructing exactly. Each layer's threshold is
   `k * sigma_j` (`k = 3 * denoise/100`), and the coefficients are shrunk with a
   **non-negative garrote** (`w * max(0, 1 - t^2/w^2)`): noise-level coefficients
   go to zero while strong ones - stars, filament edges - keep almost all their
   amplitude (a soft threshold would dim every star by `t`).
   `sigma_j` (`layer_noise`): the finest layer reads its own MAD; the coarser
   layers follow the white-noise model `sigma * n_j` (`n_j` the known per-layer
   response to unit white noise), with `sigma` read off whichever of the two
   finest layers gives the higher value. Real data is rarely white noise:
   debayering, the sub-pixel registration of every stacked frame and JPEG
   compression correlate it over a pixel or two, which drains the finest layer.
   On real Seestar stacks the second layer carried 3-7x what an extrapolation
   from the first predicts, so the coarser grain and the colour mottle passed
   through untouched whatever the setting. The coarser layers are *not* measured
   themselves: there, faint stars and nebulosity outweigh the noise (a dense
   Milky Way field read 20-60x the model at layer 4), and thresholding on that
   blurred the field into a haze.
   The threshold also follows a local noise map (the finest layer's smoothed
   energy), so a stretched frame's noisier background is cleaned harder than its
   brighter object. Each coefficient is capped at 3 noise sigma before it enters
   that map: uncapped, a star read as local noise and raised the threshold round
   itself up to the 4x ceiling, eating its faint neighbours (a faint star beside a
   bright one kept 39% of its peak; 73% with the cap). Four layers. The former
   bilateral filter flattened faint stars and left a plastic texture.
   With `denoise_engine = "deepsnr"` this stage instead runs the DeepSNR model
   **early** (see "Quality path" below); the classical stage here becomes a no-op
   and the 0-100 value blends DeepSNR's output back.
15. **Chroma denoise** (`chroma_denoise`, 0-100) - the same starlet shrinkage on
   the Cr/Cb planes only (`COLOR_BGR2YCrCb`), one layer deeper (five) and harder
   (`k = 4 * amount/100`, one global threshold), luma untouched. Colour speckle
   is usually more objectionable than luma noise in a stacked astro frame, and
   can be smoothed much harder than luma without an apparent loss of detail,
   since detail lives almost entirely in luma.
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
17. **Sharpness** (0-2) - below 1.0 Gaussian blur. Above 1.0 the two finest
    starlet layers of the luma plane are boosted by `1 + 1.5 * (sharpness - 1)`,
    but only where a coefficient clears 3 noise sigma of its own layer (the same
    garrote weight and `layer_noise` as denoise - extrapolated from the finest
    layer, a stack's correlated grain cleared it and was sharpened too) - stars
    and fine filaments sharpen, the background grain is not
    amplified, and colour is untouched (no coloured fringes). The former 3x3
    Laplacian kernel sharpened the grain as much as the signal.

Preview path downscales to 512 px (`preview_max_size`) for instant feedback; the
full-resolution result is computed on demand or via the job queue.

**Star removal splits this list.** When `star_removal > 0` (see "Star removal
(starless)" below), stages 0-4 (geometry + the sky/optics corrections) run on
the whole frame, then the stars are pulled out, stages 5-17 run on the
*starless* image, and a final `star_recombine` step screen-blends the stars
back. `star_removal = 0` (the default) runs the flat list above unchanged. The
split and the recombine exchange `float32` with the pipeline (the classical
split round-trips to uint8 internally; StarNet2 does not).

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

GraXpert's ONNX denoise model was evaluated first (2026-09-05) and not adopted:
its contract (256 px tiles blended at a 128 px stride, inputs normalised by the
image's median/MAD, a model-specific clip threshold) is not something a generic
"bring your own model" switch can drive, and the model file is fetched from a
private bucket, so there was nothing an operator could point at. Background
extraction is classical for the same reason (see "Post-stack" below); GraXpert's
AI mode would only come back the same way as StarNet2, as an external engine.

`star_removal_engine` (`"classic"` / `"starnet2"`) and `denoise_engine`
(`"classic"` / `"deepsnr"`) pick the backend per edit; the ML choice is honoured
only when the matching `AppSettings` path points at a working binary (probed by
`app.services.engine_probe`), and any failure - missing binary, non-zero exit,
timeout, bad output - logs and falls back to the classical code.

- The shared machinery is `app.services.external_engine`: `run_cli` writes the
  input, runs `<tool> -i … -o … -q [-s stride] --machine-progress`, and reads the
  result back **at the input's depth** - an 8-bit round trip posterises exactly
  the faint signal these models exist to recover. `uint8` / `uint16` BGR goes
  through a TIFF of the same depth (`cv2` swaps BGR/RGB both ways, so the round
  trip is identity); `float32` is linear data and goes through a 32-bit FITS cube
  (clipped to `[0, 1]`, which both tools require) with `--linear`, under which
  each tool applies its own reversible MTF around inference. `ModelEstimateCache`
  stores the output per session as a lossless `.npy`, keyed on the pixels fed to
  the stage, their dtype and the engine settings (the editor re-runs the pipeline
  on every slider move, so an edit that doesn't touch those must reuse the
  estimate).
- **StarNet2** (`external_starless`): `apply_parameters` takes a `starless_split`
  override at the existing split point; the stretched frame is sent as a 16-bit
  TIFF, `blend_starless` applies `star_removal` exactly as the classical split,
  and the recombine step is unchanged.
- **DeepSNR** (`external_denoise`): `apply_parameters` takes a `denoise_stage`
  override. On a **stacked composite** it runs on the **linear** data, ahead of
  the `stack_base` pre-stage - before any stretch amplifies and reshapes the
  noise; a NAFNet restoration model trained on stacked astro data wants exactly
  that, and keying the cache on the linear composite means no Stack-step or
  creative edit re-invokes it. On an ordinary image it runs right after the
  background corrections, as a 16-bit TIFF. The classical `denoise` creative
  stage is dropped when this is active; `blend_denoise` applies the 0-100
  strength. If a pass fails on linear data, the fallback is a per-plane starlet
  denoise of the linear planes (`apply_linear_denoise`).
- A pass is seconds to minutes, so it streams. Both tools emit `--machine-progress`
  JSON Lines on **stderr**
  (`{"schema":"starnetastro.cli.progress.v1","event":"progress",…,"percent":P}`,
  `P` 0-100); `_run_streaming` reads them off a merged pipe, `_parse_progress`
  pulls `percent`, and each is forwarded to the job's `on_step` across a band
  (`_DEEPSNR_PROGRESS_BAND` 12-40, `_STARNET2_PROGRESS_BAND` 20-80); job progress
  is made monotonic so later stages can't pull the bar back.
- No new Python dependency: each CLI is self-contained (its own ONNX Runtime).
  Verified against StarNet2 2.6.1 / DeepSNR 1.3.1 (linux-x64) on the Debian-13 image.

## Looks (the "Style" step)

`LooksService` (`app/services/looks.py`) - an optional finishing look, chosen in
the "Style" step just before Export, that turns a clean result into a shareable
one. It runs **last**, as a separate layer on the pipeline's finished 8-bit
result (`ImageProcessingService.apply_look`, after `star_recombine` when star
removal is active). The job keeps that pre-look result losslessly
(`prelook.npy`, keyed by a hash of every parameter but the look plus the
source's mtime), so changing only the look or its amount re-applies it in
milliseconds instead of re-running the pipeline, the gallery thumbnails are
rendered from a ~400 px copy, and an export "without style" is exact. No look
is an identity. What the user sees: [FEATURES.md](FEATURES.md#style).

**Guardrail - no invented detail.** Every operation only redistributes the
recorded signal: tone, colour, contrast at a given scale, a glow built from the
image's own bright areas. No synthetic stars or diffraction spikes, no sky
replacement, no generative model. Tests check that no look creates fine
structure on a flat frame or raises the pixel-scale grain of a pure-noise sky.

**Size-relative.** Every radius is a fraction of the image diagonal, so a
~320 px gallery thumbnail previews the full-resolution export faithfully (a test
compares "style then shrink" with "shrink then style").

Building blocks (each an identity at strength 0, BGR float32 in and out):

- **Local contrast** - a difference of Gaussians of the luminance (0.2 % and
  2 % of the diagonal, the fine one at least 1 px) added back to every channel.
  Band values within 3 noise sigmas (MAD of the band, which is mostly sky) fade
  out through a non-negative garrote, so grain is never boosted. Stars sit in
  the same band and would bloat, so they are shielded (see "Stars" below), and
  lifts fade out over the top half of the range (`2 * (1 - L)`), so a bright core
  (the Lagoon's, Orion's) keeps its detail instead of burning to white.
- **Orton glow** - a blurred copy (1.2 % of the diagonal), minus its own median
  so the sky contributes nothing, screen-blended on top.
- **Deep sky black** - a soft toe on the luminance,
  `L' = L * L / (L + k) * (1 + k)` with `k = strength * median(L)` (capped at
  0.5); colours are scaled by `L' / L <= 1`, so nothing brightens and white stays
  white.
- **Colour pop** - luminance-preserving saturation weighted by an object mask
  (blurred luminance from the sky median to the 99th percentile), so the
  target's colours deepen and the background's colour noise does not. Only the
  smoothed colour (1 px+ blur of the chroma) is boosted: pixel-scale colour
  grain is never amplified.
- **Split toning** - a cool tint on the background and a warm one on the
  subject (same object mask). The tints carry zero luminance and scale with each
  pixel's luminance, so brightness is unchanged and black stays black.
- **Vignette** - a smooth corner darkening (up to 35 %), flat in the centre.
- **Warm / cool tone** - a luminance-free amber or teal tint proportional to
  each pixel's luminance (black stays black).
- **Shadow lift** - colours scaled by `1 + 0.6 * s * (1 - L)^2`: darks open up
  by at most 1.6x, white not at all; a gain, never a grey offset.
- **Inner glow** - the Orton glow for a subject that fills the frame: its floor
  is the 20th percentile instead of the median (a frame-filling nebula *is* the
  median), and its source leaves the stars out, so a bright star does not swell.
- **Star glow** - the detected stars' own pixels, blurred (0.4 % of the
  diagonal) and screen-blended back: a round bloom, never a spike.
- **Star colour** - the smoothed colour boosted on the star pixels only
  (typical-size star mask, scaled so a 75th-percentile star gets the full boost),
  so the nebulosity round a bright star is never tinted with a disc of colour.
- **Core and arms** - a luminance-free warm tint growing with the subject mask
  squared (the core) and a cool one with `m * (1 - m)` (the fainter outskirts):
  a spiral galaxy's old yellow core and young blue arms.
- **Disc detail / band detail** - for the Moon and planets, whose disc may be a
  few dozen pixels in a big black field: the disc is found by Otsu's threshold
  on the luminance, and the scales are fractions of *its* equivalent diameter
  (craters: 0.4 % to 4 %; a planet's belts: up to 10 %), not of the frame. The
  band-pass is a blur normalised over the disc only, so the sky never enters it,
  and it fades in from the limb over 2 % of the diameter: no ring on the limb.
  The noise is read at pixel scale (a detailed disc is all structure, so the
  band's own spread is not noise) and scaled to the fine blur; lifts fade
  towards white. No disc wider than 8 px: nothing to sharpen.

**Stars.** A star is a compact bright peak: the luminance above its own blur at
0.3 % of the diagonal (at least 1.5 px) by more than 5 noise sigmas. Bright
stars, whose halo is wider, are found again at three times that radius - but
only round the image's brightest 0.3 % of pixels, because at that scale a thin
nebula filament is a "peak" too and must keep its boost. The shield used by
local contrast is these masks grown by twice their radius and softened.

**Night landscapes.** When the session's composite has a sky mask (an iPhone
ProRAW, single or stacked - see "Nightscapes"), the gallery also offers
`galactic_core` and `blue_hour` (`GET /api/looks/{id}` lists them first). These
looks have sky steps and foreground steps: each runs with its statistics
measured on its own region, and the two results are blended through the mask,
feathered over 0.2 % of the diagonal. The mask is taken through the edit's
geometry first (`EnhancementService.look_sky_mask`, on a copy at most twice the
target size, so a thumbnail never warps a full-resolution mask). On the sky:

- every blur is normalised over the sky only, so the sky next to a tree line is
  averaged with sky, never with the dark foreground;
- the sky's local level ignores "sky" pixels darker than 0.75x that level: the
  phone's matte is coarser than a tree, and dark leaves it counts as sky would
  otherwise pull the level down and make the sky beside them glow (a halo);
- the "subject" (for toning and colour pop) is what stands out from the local
  sky level (6 % of the diagonal), not the sky's broad brightest gradient - the
  light-pollution dome over the horizon is not warmed as if it were the Milky
  Way - and it fades out over a 1 % strip of sky along the foreground.

Without a sky mask (an API call on an ordinary image), these looks apply their
sky steps to the whole frame.
Looks (weights at amount 100; `amount` scales them linearly):

| Look | Operations |
|------|------------|
| `vivid` | deep sky black 0.5, local contrast 1.0, colour pop 1.0 |
| `soft_glow` | deep sky black 0.4, Orton glow 1.0 |
| `cinematic` | local contrast 0.3, split toning 1.0, vignette 0.6 |
| `galactic_core` | sky: local contrast 1.0, split toning 1.0, colour pop 0.8; foreground: shadow lift 0.7, local contrast 0.3 |
| `blue_hour` | sky: cool tone 1.6, Orton glow 1.0, local contrast 0.4; foreground: shadow lift 0.6, warm tone 1.0 |
| `luminous` | deep sky black 0.4, inner glow 0.8, colour pop 1.0 |
| `structure` | deep sky black 0.3, local contrast 1.6, colour pop 0.5 |
| `deep_field` | deep sky black 0.7, local contrast 0.8, star glow 0.4 |
| `warm_core` | deep sky black 0.3, core and arms 1.0, colour pop 0.6 |
| `sparkle` | deep sky black 0.3, star colour 1.0, star glow 1.0 |
| `night_velvet` | deep sky black 1.6, star colour 0.6, vignette 0.5 |
| `moon_crisp` | deep sky black 0.3, disc detail 1.0 |
| `moonlight` | disc detail 0.4, Orton glow 0.7, cool tone 1.0 |
| `planet_crisp` | deep sky black 0.3, band detail 1.0 |
| `rich_colour` | band detail 0.5, colour pop 1.2 |

The gallery groups the looks by kind of picture (`GET /api/looks/{id}`): any
image (`vivid`, `soft_glow`, `cinematic`), night landscape (with a sky mask
only), nebula (`luminous`, `structure`), galaxy (`deep_field`, `warm_core`) and
star cluster (`sparkle`, `night_velvet`), Moon (`moon_crisp`, `moonlight`) and
planet (`planet_crisp`, `rich_colour`). It opens on the night-landscape group
when there is a sky mask; otherwise on the group of the built-in preset the user
applied (Nebula, Galaxy, Cluster, Lunar), else on "any image". The kind of
target is never guessed from the picture; one tap on a chip switches group.

Tuned on real stacks - smart-telescope FITS and DSLR / astro-camera linear
TIFFs of nebulae, galaxies and clusters - each opened the way the app opens it,
and on telephoto Moon shots. The planet looks are so far checked on synthetic
banded discs only.

## Auto Astro (one-click adaptive enhancement)

`AutoAstroService.suggest_parameters(image, sky_mask, wide_field=...)`
(`app/services/auto_astro.py`) measures the picture an edit starts from and
proposes the finishing edit that showcases it. That picture
(`EnhancementService.analysis_view`) is, for a stacked composite, a fresh render
of its "Stack" step with the session's own settings - not the stored original, a
JPEG of the default render made by whichever version ingested it - and, for an
ordinary upload, the upload. The route carries the "Stack" settings, the framing
and the "Style" look through unchanged.

**Measurements** (`measure`, everything on the 0-255 display scale). The
regions are found on a copy downscaled to 800 px and median-filtered (5x5, which
wipes the stars): the **background** is the darker 40% of the sky, the
**object** what rises above the background by more than 30% of the way to the
99th percentile - the nebula or galaxy body, not the stars. A night landscape's
sky mask restricts both to the sky. Then: the sky level and each channel's
(median over the background of a 7x7 local mean - what the eye sees and what the
denoise leaves: a dark sky's noisiest channel clips at 0 most, so its raw median
sits under its mean, and a sky neutral by the median came out blue once
denoised), with each channel's histogram over the background; the object level
(median luminance) and colour
(mean max-min channel spread); the object's green excess (mean `G - (R+B)/2` as a
fraction of its luminance - signed, so the noise does not count); the background
noise of the luminance and of the noisier chroma plane (MAD of the finest
starlet layer, as a white-noise sigma); the detected stars per megapixel.

**Scene.** A sky under 6 with almost no noise (sigma under 1) is a **bright
object on black** - the Moon or a planet. A sky mask, a wide-field lens
(`RenderHints`) or a sky brighter than 60 (a light-polluted wide field, a phone's
processed night shot) makes a **night landscape**. Anything else is **deep sky**.

**Tone curve** (all but the Moon and planets). A master curve through `(0, 0)`,
`(sky, 0.6 * sky)` (never more than 25 levels down), `(object, object + 0.5 *
(128 - object))` (never down, and never climbing more than 3x as steeply as the
sky-to-object span: a faint object - a JPEG of IC 5070, 18 levels above its sky
- asked for ~4x, which posterised 8-bit data and multiplied the noise just above
the sky as much) and `(255, 255)`, drawn by the editor's monotone cubic: black stays black and nothing clips, the sky deepens and the object moves
toward the midtones - the separation that makes an object stand out. No curve
when the object is within 12 levels of the sky. It shows in the curve editor like
any curve. A **sky cast** is additive (skyglow), so each channel whose sky - as
the master curve leaves it - is a level or more off the grey of the same
brightness gets its own curve, moving its sky onto it and converging to identity
in the highlights (the "levels per channel" neutralisation of a photo editor).
"As the master curve leaves it" is the mean of the curve over the channel's
background histogram, not the curve at its sky level: the noise straddles the
bend where the curve steepens above the sky, which lifts the mean, and a channel
whose sky sits lower, on the straight part, is lifted less - neutral by the
curve at the sky level, the result kept a 3-4 level cast. The channel curve's
point is solved the same way, by bisection on the channel's histogram: lifting a
starved channel takes a strongly concave curve, whose mean over a noisy sky falls
short of its value at the mean (a JPEG of IC 5070 kept a 4-level red cast). A stacked
composite's sky is already neutral (colour calibration), so this mostly serves
JPEG uploads: a Seestar JPEG of IC 5070 came in at B 32 / G 33 / R 23 and came
out at 19 / 16 / 18.

The tone sliders are not used. An earlier version stretched with `contrast` /
`exposure` and deepened the sky with `shadows = -0.35`: on real stacks that
crushed the sky to black (the M31 mosaic: sky 28 -> 3 of 255, 24% of the sky at
0-2, the galaxy's outer halo gone; a NGC 281 JPEG: 32 -> 5, 19%), and the equal
subtraction from every channel turned a faint cast into a magenta or blue tint.
It also measured a composite's already-stretched render and stretched it again.

**Noise.** The denoise strengths are thresholds relative to the measured noise
(see "Denoise" above), so they encode how visible the noise is - its sigma
times the tone curve's gain from the sky to the object, since the denoise runs
after the curve: `denoise = clip(10 * (sigma * gain - 0.5), 0, 40)` and
`chroma_denoise = clip(14 * sigma_chroma * gain, 0, 60)`, at least 50 for a
camera night landscape (an iPhone ProRAW arrives denoised at the finest scale -
its sigma reads low - but carries coarse colour blotches). Calibrated on real Seestar
stacks (luma sigma 3-6) and JPEG uploads (1.5-4): a luma setting above 40
smeared the faint stars of a dense field into a haze; colour takes a harder cut
since it carries little detail.

**Colour.** `green_removal = 50` when the object's green excess is over 3% (a
one-shot-colour sensor's extra green; a blue reflection nebula or a red emission
nebula reads negative and is left alone), never on the Moon. Deep sky only:
`vibrance = 1.15 + 0.35 * clip((80 - object_chroma) / 80, 0, 1)` - the
colour-preserving stretch leaves the colour pale, a galaxy's most of all. A night
landscape gets no boost: its render is already saturated, and the boost made the
Milky Way's colour mottle garish.

**Stars.** Deep sky only: `star_reduction = clip(5 * ln(1 + density) - 10, 0,
30)` - real fields span tens to 4000+ stars per megapixel, hence the log. A
night landscape's stars are its subject; on the Moon the "stars" are craters.

**Moon and planets** get only noise-aware sharpening (`sharpness = 1.3`).

Never set: `gradient_reduction` and `vignette_correction` (below), saturation,
clarity, the white balance sliders, and the engines (DeepSNR / StarNet2).

**Checked against real images.** The opt-in benchmark
`tests/benchmarks/test_auto_astro_real_images.py` runs the whole path (ingest,
Auto Astro, render) on a folder of real captures and checks that the sky is
deepened but never clipped, stays neutral, and gets no more visibly noisy (a
sigma under 1 of 255 is invisible); it also writes before/after comparisons to
look at. It caught the refinements above - the sky's mean colour, the curve's
gain - that a fit-to-screen look had missed. Synthetic tests guard the *shape* of each
rule; they cannot replace checking real output before shipping a number that
runs unsupervised - every rule above was settled on real captures (Seestar
stacks and JPEGs, iPhone ProRAW night landscapes, lunar JPEGs).

**Gradient reduction (tried, removed)**: light pollution / vignetting shows up
as a broad brightness trend across the frame, so the first version fitted a
plane (least squares) to a heavily blurred copy of the frame and used the
fitted plane's corner-to-corner amplitude as severity - deliberately not the
blurred frame's raw standard deviation, since a centred, radially-symmetric
DSO also strays from flat under a heavy blur just as much as a real gradient
would, but contributes almost nothing to a best-fit *linear* plane (a
symmetric bump's slope cancels out around the centre). That fix genuinely
worked against a synthetic centred-circle test (an earlier std-based version
had suggested `gradient_reduction=42` on a perfectly flat background with
nothing but a centred bright circle on it; the plane-fit version correctly
read that as flat).

It failed against real photos anyway. Checked against a library of real
stacked FITS composites and real lunar photos: an ordinary, uncropped lunar
shot - no light pollution gradient to correct, nothing subtle about it - measured
a severity of 0.049-0.071, landing squarely inside the same range several
legitimate-looking real deep-sky corrections measured (0.02-0.16). A real
photo is essentially never perfectly symmetric (off-centre framing, a
lunar terminator, an elongated galaxy), so the false-positive rate in
practice was too high to trust unsupervised - the same structural confound
that already ruled out an auto vignette-correction heuristic (a real vignette
and a centred bright object produce the identical centre-bright/edge-dim
radial signature; no single-frame trick tells them apart). `gradient_reduction`
is manual-only; `AutoAstroService` never sets it.

**A note on very bright stars**: by the time `star_reduction` runs (after the
tone stages, see the pipeline order above), a star that was already near-white
can be a wide, flat, saturated plateau with little gradient left for erosion to
shrink into. This reads as a small round white disc even after reduction -
expected for a frame's few brightest "anchor" stars (real astro-processing tools
leave these visible after reduction too), not a defect in the shrink algorithm
itself. Actually removing a star regardless of brightness is the separate, more
aggressive "Star removal (starless)" operation above (`star_removal` /
`star_recombine`), not reduction.

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
4. **Polynomial refinement** (`refine_warp`, `similarity` / `affine` only). A
   wide-angle lens' distortion makes stars drift differently across the field
   as the sky turns: on a real iPhone series (24 mm equivalent, 4 minutes) the
   global transform left 1.65 px of residual (half resolution), growing toward
   the edges, and the corner stars of the stack came out as short streaks. So
   every detected star (not just the 60 brightest) is paired with its mutual
   nearest reference star within 3 px of the global transform, and a cubic
   polynomial reference -> source warp is fitted with 3-sigma MAD rejection. It
   replaces the global transform only with at least 60 pairs covering 7 of the
   9 cells of a 3x3 split, a residual cut by at least 20%, and nowhere more than
   2% of the frame diagonal away from the global transform - a deep-sky field
   (no distortion, fewer stars) keeps the global transform. On the iPhone series:
   residual 1.42 -> 0.64 px, and the stack's median star size 4.62 -> 4.08 px,
   the same as a single frame (4.05; corners 4.86 -> 3.79). The align pass then
   warps with `cv2.remap` (Lanczos) instead of `warpAffine`. A forward
   polynomial (source -> reference) is fitted on the same pairs for drizzle,
   which places each input pixel and checks it against the 1x median with that
   same warp - placing with the global transform against a warp-aligned median
   rejected clearly more star pixels toward the edges. The warp is saved in the
   stack checkpoint, so a resumed re-combine or drizzle uses it too.

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
   **iterative sigma-clip** (2 iterations, k=3). The first iteration is centred
   on the **median with a MAD spread** (sort-based, NaN-aware - as fast as a sum
   and far faster than `np.nanmedian`; the plain std stands in where the MAD is
   0), the second on the mean / std of the samples - those the first kept
   (`sigma`), or all of them clamped into the first pass's bounds
   (`winsorized_sigma`, the Siril / PixInsight estimate). Either way the
   samples outside the final bounds are **dropped**. The robust first pass is
   what removes a one-frame aircraft or satellite trail from a short stack: a
   mean / std that includes the outlier can place it at most `(N-1)/sqrt(N)`
   sigma away (2.85 for 10 frames, under k=3), so a plain sigma-clip would keep
   it and average it in at 1/N. Winsorization only *estimates* the spread: the
   former `winsorized_sigma` kept the clamped samples in the mean, which adds
   k sigma / N wherever an outlier is one-sided - a faint line left along every
   trail. Then a **weighted mean** (`none` = equal / `noise` = `1/noise^2` clamped 0.25-4x /
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
and capped at 4, `stacking_workers` to tune). Threads not processes, which is
fine because the per-frame hot path
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
2. **Sky neutralisation** (always, `app/services/color_calibration.py`
   `neutralise_sky`) - each channel's sky level (its median over the darker half
   of the frame by luminance) is subtracted **without clipping**: the noise keeps
   its negative half. Clipping it at zero, as the former stretch did, leaves a
   positive bias proportional to each channel's noise, which a later channel gain
   (a Seestar's weak blue is boosted ~4x) turned into a purple, mottled sky.
   *Which* pixels are the darker half is decided on other pixels than the ones
   measured: the smoothed luminance of a 1-in-4 lattice selects the pixels of a
   second lattice offset by half a step. Chosen on their own values, the choice
   followed each pixel's noise - and luminance is 72% green, so the "darker"
   pixels were the ones whose green noise happened to be low. Green's sky level
   came out lowest, too little of it was subtracted, and every stretched
   composite had a green sky (NGC 7023, 60 frames: R 25 / G 28 / B 22 of 255;
   26 / 26 / 25 since). When too few stars are measured for the colour
   calibration below, its fallback (`calibrate_colour`) runs on the data from
   before this step, which zeroes each channel's sky itself: clipping the
   neutralised data at zero would cut off the negative half of the sky noise.
3. **Colour calibration** (`color_calibration`, on/off, `star_white_balance`) -
   **the star field is the white reference.** Stars are detected on a band-passed
   luminance (Gaussian 1 px minus 6 px, 8 sigma, 4-400 px components) of a copy
   downscaled to <=2048 px (INTER_AREA keeps flux ratios); each unsaturated star
   (no channel above 0.9) is measured by aperture photometry against the median
   of a surrounding annulus (the local sky, so a star on a nebula is not tinted
   by it); the median `R/G` and `B/G` of the 400 brightest set the gains, which
   are normalised to keep luminance. A field's star population averages out close
   to neutral, so - unlike the former "balance the channel means", which a red
   emission nebula or the blue Pleiades pulled toward grey - the target keeps its
   real colour. Verified on four real Seestar stacks: M31's weak blue got a 4.6x
   gain (the old method clamped at 4x), NGC 7000's frame-filling H-alpha stays
   red instead of being neutralised to grey-pink, and the Pleiades reflection
   nebula comes out blue. With fewer than 20 clean stars the former
   means-balance runs as a fallback.
4. **Stretch** (`stretch`, 0-1; `stretch_mode`) - `stretch` sets the target sky
   level by log interpolation (0 -> 0.05, 0.5 -> 0.10, 1 -> 0.20), so higher
   pulls up fainter signal at the cost of a brighter, noisier background.

   `stretch_mode = "adaptive"` (default, `app/services/stretch.py`) stretches
   **luminance** and carries colour as a ratio, `rgb * L'/L` (Lupton et al.
   2004; Siril's colour-preserving asinh), so hue and saturation survive. The
   curve is chosen per image from a one-parameter family by bisection so that two
   measured levels land where they should: the **sky** (10th percentile of a
   star-suppressed copy - a 5x5 median on a <=800 px downscale - not the frame
   median, which on a frame-filling nebula *is* the nebula) maps to the target,
   and the **object** (99th percentile of the same copy - the nebula / galaxy
   body, not the star cores) maps to 0.72. Negative family values lower the white
   point (a midtone transfer - lifts a faint object); everything above 0.6 of
   that lowered white rolls off through a log **highlight shoulder** (unit slope
   at the knee, the true white landing exactly on 1, the role of GHS's highlight
   protection) instead of clipping, so nebula filaments and stars brighter than
   the object keep their gradation and colour. A low-contrast object (only a few
   times the sky) may then stop short of 0.72 at the lowest family value - the
   price of not burning everything brighter than it. Positive values keep
   the white point and put an arcsinh stage under the midtone transfer
   (compresses highlights - a bright core keeps its structure). The black point
   is the sky minus 2.8 noise sigma, the noise read as the MAD of a 3x3-median
   residual on the darkest 30% of the sky. A pixel whose brightest channel would
   exceed 1 is **desaturated toward its own stretched luminance** just enough to
   fit - scaling it down instead darkens it (a dark ring round every bright blue
   Pleiades star). Where the *source* composite was near saturation (> 0.9) the
   colour is an artefact of one channel clipping first, so the pixel is faded to
   neutral. On the reference Seestar stacks: M31's core, which the classic
   stretch clipped to a flat white disc although it sits at ~0.64 in the linear
   data (sky 0.426), keeps its gradient; star cores keep their colour. About
   0.7 s for the stretch at 8 MP; the whole pre-stage costs about what the
   classic one did.

   `stretch_mode = "classic"` is the former stretch, kept for comparison and for
   older edits: sky neutralised by subtracting each channel's low percentile
   (clipped), then **one** MTF stretch, derived from the luminance after a
   99.9th-percentile clip, applied to all three channels - brighter, but it clips
   galaxy cores and pushes stars to white. It also keeps the former means-based
   colour calibration.

**Nightscapes (a sky mask).** A Milky Way shot usually has a landscape in the
frame, and every step above measures "the sky" from statistics a dark landscape
corrupts: the background fit only rejects tiles *brighter* than the surface, so
trees are fitted as sky and drag it down (a halo round every tree); the sky level
is the darker half of the frame (the trees); the stretch's black point and sky
come from the darkest pixels (the trees again). When the composite has a **sky
mask** (`sky_mask.npy` next to `composite.npy`, high = sky - see
`app/utils/sky_mask.py`; today Apple ProRAW's own `semanticskymatte`), every
step measures the sky alone:

- background extraction samples only lattice tiles that are at least half sky,
  from their sky pixels; never drops a tile for *touching* the landscape (that is
  the sky right above the horizon, where the light-pollution dome is); fits a
  **cubic** (the dome climbs steeply toward the horizon) - except on a
  wide-field frame, which gets a plane (see `wide_field` below); skips the
  frame-edge correction (that edge is the
  landscape, not a stack footprint); and subtracts the surface **from the sky
  only**, feathered across the horizon (mask grown by twice the ramp first, so the
  ramp falls on the dark landscape side - a ramp on the sky side left a bright rim
  round every tree). The landscape keeps its own tones.
- sky neutralisation takes the darker half *of the sky*.
- **the camera's white balance is kept**: the star white balance is skipped. On
  real iPhone ProRAW frames its gains cut blue by about a third (the phone lens'
  blue fringing and the skyglow round each star bias the star colours) and cast
  the Milky Way yellow-green, while the camera's own balance looked natural.
- the stretch reads the sky level, noise and object level inside the mask.

A mask with less than 1% landscape counts as no mask, so an all-sky frame takes
the deep-sky path unchanged.

**Render hints (`RenderHints`, `render_hints.json` next to the composite).** What
the source frames say, recorded at ingest (`linear_ingest._ingest_raw`) and kept
with the composite:

- `camera_processed` - every frame is a linear DNG (a phone's ProRAW: merged,
  denoised and white-balanced by the phone). Its **white balance is kept** (the
  star white balance is skipped, as for a nightscape: it cast real iPhone frames
  yellow-green), and a stack of them uses **equal weights** instead of the
  default noise weighting - the phone denoises each frame by its own
  ISO-dependent amount, so on a real 12-frame iPhone series the ISO 10000 frames
  read 3x "cleaner" than the ISO 2500 ones and got 10x the weight. The weighting
  actually used is recorded in `quality_report["weighting"]`.
- `wide_field` - the EXIF 35 mm-equivalent focal length is at most 50 mm: a Milky
  Way / landscape lens. Two things change. **Vignetting is divided out first**
  (`devignette`): such a lens' linear data falls to about 1/3 in the corners (an
  iPhone main camera: 0.26-0.38 on five frames from two nights, with and without
  a Milky Way in the frame) and nothing in the file corrects it - the phone
  hides it in its own render. With no flat to calibrate against, and a Milky Way
  that can cross the centre (a free radial fit absorbs it), the model is fixed to
  the natural `V(r) = (1 + a r^2)^-2` shape, one `a` per channel (phone lenses
  shade colour too), with `r` measured on each axis over its own half-length
  (circular in sensor coordinates, elliptical in pixels: a radius over the
  half-diagonal left the iPhone frames ~45% too bright at the long axis's ends,
  a U-shaped residual, while this one fitted the same strength on both axes), fitted in log space on the 15th percentile of each ring
  around the centre from r = 0.3 outward (a band covers a small arc of each ring;
  the rings nearer the centre can lie wholly inside it), landscape pixels
  excluded. A fit implying corners above 0.9 or below 0.15 is not applied. Then
  the sky's remaining **colour shading is flattened** (`flatten_sky_colour`):
  the same iPhone frames still drifted about +15% blue toward one corner and 12%
  less red along the bottom (a green glow once stretched), identically on every
  frame and on their stack. Degree-2 surfaces are fitted to the sky's R/G and
  B/G ratios (16x12 lattice, each tile's darker pixels, the brightest 30% of
  tiles - the Milky Way's own colour - left out, 2-sigma rejection), normalised
  to their median, and R and B divided by them: colour only, so it cannot carve
  the Milky Way's brightness. Then **background extraction fits only a tilted
  plane** and skips the border correction, with or without a sky mask: a curved
  surface bends to the Milky Way's broad glow, carving dark holes into it (under
  a mask the cubic took up to 87% of a broad synthetic band), and on a real
  iPhone frame below a town's light dome the cubic - its outlier rejection
  dropping the dome's bright tiles - left a dark arch above the horizon and
  bright lavender sides. The plane takes the overall tilt and leaves the glow
  at the horizon. Finally the stretch (`adaptive_stretch(wide_field=True)`)
  **keeps the darkest real sky above the black point** (black <= the sky's
  0.5th percentile minus 15% of its distance to the sky level - a stack's low
  noise otherwise lifts the black point, sky - 2.8 sigma, up to the sky level,
  and the slightly darker parts of a never-quite-flat wide-field sky were
  crushed to black blotches) and **fades the colour toward grey where the
  signal is near the noise**: each pixel keeps `s / (s + 8 sigma)` of its
  colour, `s` its level above the black point - about a quarter on the sky, two
  thirds on the Milky Way's bright parts, nearly all of it in a star. The
  stretch carries colour as a ratio to the luminance, and 2.8 sigma above black
  that ratio is mostly colour noise. A deep-sky stack's colour noise is
  fine-grained and the chroma denoise takes it, but a phone merges and denoises
  its night shot into noise at every scale up to tens of pixels (on real iPhone
  frames the coarser wavelet layers carry 20-50x the white-noise level), and
  the Milky Way came out under green and magenta blotches - the phone's own
  render, far flatter, showed none. A stack, with less noise, keeps more of its
  colour. Not solved: a single frame cannot tell the vignetting from a glow
  that rises toward a frame edge, so a frame with a strong horizon glow can
  keep a brighter edge (asking the photographer for flat frames is out of
  scope).

A **stack** of ProRAW frames gets its mask from the **reference frame**: each
frame's matte is stored with it at upload (`frames/NNNN_sky.npy`), every frame is
warped into the reference's geometry, so the reference's matte is resized to the
composite (drizzle included), given the same wedge crop, and stored as the
stack's `sky_mask.npy`. The landscape itself is still aligned on the stars, so it
blurs over a long series; stacking sky and landscape separately is not done yet.

Nothing here touches `composite.npy`; every value recomputes the working image
from the linear data, so the stretch/background/colour choices stay reversible
and never lose highlight or shadow detail to an early 8-bit quantisation.
Photometric (catalogue-based) calibration would need plate solving and is not
done; the star-referenced white balance above is the catalogue-free equivalent.

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
| Denoise (starlet, 4 layers, luma) | ~300 ms (measured at 8 MP) |
| Chroma denoise (starlet, 5 layers, Cr/Cb) | ~400 ms (measured at 8 MP) |
| Stack pre-stage, adaptive (background + calibration + stretch) | ~1.1 s (measured at 8 MP) |
| Depth map (Sobel) | 50-100 ms |
| Stacking, per frame (calibrate + register at half-res + align at full-res debayer + combine) | ~0.4-1 s (three IO passes, run across `stacking_workers` threads) |

Whites/blacks and highlights/shadows cost the same shape of work (a full-res
grayscale conversion + masked blend) but were measured at different times -
if you see one much cheaper than the other, re-measure both rather than
trusting either number blindly.

The whole pipeline runs as a background job, off the request path; the
editor's 512 px preview keeps slider feedback fast while the full-resolution
render is produced on demand.
