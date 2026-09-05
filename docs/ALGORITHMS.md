# Processing algorithms

Reference for the image processing pipeline. Implementations live in
`app/services/image_processing.py`, `app/services/star_detection.py`,
`app/services/depth_map.py`, and the stacking services. All functions operate on
BGR `uint8` numpy arrays unless noted.

## Single-image pipeline

Applied in this order to minimize artifacts (`apply_parameters`):

0. **Geometry** (`geometry`) - quarter turns (clockwise), then flips, then
   straighten (`cv2.getRotationMatrix2D` + `warpAffine`, scaled up by
   `max((w·cos+h·sin)/w, (w·sin+h·cos)/h)` so the frame stays full), then the
   crop rectangle. Runs first; it changes the working dimensions.
1. **White balance** (`temperature`, `tint`) - per-channel gain in linear RGB;
   6500K is neutral. Warm shifts reduce blue, cool shifts boost blue.
2. **Contrast** (`contrast`, 0.5-3.0) - linear scaling around the image mean,
   `y = (x - mean) * contrast + mean`, then a mild gamma for a smooth response.
3. **Brightness** (`brightness`, -1..1) - pixel offset, `beta = brightness * 50`.
4. **Highlights / shadows** (-1..1) - masked tone curves; `gray^2` emphasizes
   bright regions, `(1 - gray)^2` emphasizes dark regions, scaled by 0.3.
5. **Tone curve** (`curve_points`, empty by default = identity) - a 256-entry
   lookup table (`app/utils/math_utils.py:curve_points_to_lut`), applied via
   `cv2.LUT` identically on each BGR channel (a combined RGB curve, not
   separate per-channel curves). Points are `(input, output)` 8-bit level
   pairs spanning the full 0-255 range (`ProcessingParameters` validates: at
   least 2, first at x=0, last at x=255, strictly increasing x); between them
   the curve is a **monotone cubic Hermite spline** (Fritsch-Carlson tangent
   correction), not a plain polyline - a handful of dragged points make a
   smooth curve instead of visible straight-line kinks, and the correction
   guarantees the spline never overshoots past a control point's value in the
   segments next to it (an overshoot would locally crush shadows or blow out
   highlights the user never asked for). A user-drawn curve subsumes and can
   replace manual contrast/brightness/highlights/shadows tweaking, but doesn't
   replace those sliders - both stages run, in this order, so a curve is a
   fine-tuning layer on top of the basic tone controls, matching how most
   photo editors separate "Basic" tone sliders from a "Curve" panel.
6. **Saturation** (0-2) - scale the HSV S channel.
7. **Vibrance** (0-2) - saturation boost weighted by `(1 - current_saturation)`
   so already-saturated pixels move less.
8. **Clarity** (-1..1) - unsharp mask against a 21x21 Gaussian blur; positive
   sharpens, negative softens.
9. **Denoise** (0-100) - bilateral filter; map to diameter 5-20 and
   sigma_color / sigma_space 75-150. Above 50, add a 3x3 morphological close.
10. **Star reduction** (`star_reduction` 0-100, `star_sensitivity` /
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
11. **Sharpness** (0-2) - below 1.0 Gaussian blur, above 1.0 Laplacian-kernel
    sharpen blended by `(sharpness - 1) * 0.5`.

Preview path downscales to 512 px (`preview_max_size`) for instant feedback; the
full-resolution result is computed on demand or via the job queue.

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
- `brightness` is chosen so the black point, after `apply_contrast`'s own
  mean-centered formula (`y = (x-mean)*contrast + mean`), settles near a
  near-black floor (~3) - a crushed background reads as depth, so this isn't
  protected from crushing the way an early version did (floor ~8, which read
  as flat/washed-out against a real photo).
- `highlights = +0.2` (a modest boost to the DSO's own bright detail) unless a
  meaningful fraction of pixels already clip near white (`>= 250`), in which
  case it pulls back instead.
- `shadows = -0.35` (deepens the background) unless the frame is already
  mostly near-black (`<= 5`) beyond what a typical deep-sky background
  accounts for, in which case further crushing would just eat real faint
  signal. `apply_highlights_shadows` weights `shadows` toward the *darkest*
  pixels only (`shadow_mask = (1 - gray)^2`), so this mostly darkens the empty
  sky and barely touches the DSO itself - exactly the "highlight the object,
  darken the background" separation real deep-sky processing aims for, rather
  than one flat brightness shift.
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
brightness is a different, more aggressive operation ("starless", v0.3 on the
roadmap) than reduction.

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

An ML backend (MiDaS / `Intel/dpt-hybrid-midas`) is planned for v0.2 behind
`DEPTH_DETECTION_METHOD=ml`.

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

## Stacking (v1.1)

`StackingService.process` runs: registration -> background normalisation
(optional) -> cosmic-ray masking (optional) -> combination. The composite is
saved as a normal session so the single-image routes work on it.

- **Registration** (`RegistrationService`) - ORB (default, fast) or SIFT
  keypoints -> knnMatch + Lowe ratio 0.75 -> RANSAC homography (reproj 5.0) ->
  `warpPerspective` to `frames[0]`. Needs >= 4 good matches; frames that fail are
  returned unchanged and counted in `frames_rejected`.
- **Background normalisation** (`NormalizationService`) - median of a 32 px edge
  border per frame; shift all frames to the common median.
- **Cosmic-ray masking** (`CosmicRayService.build_mask`) - per-pixel median plus
  a **MAD-based** robust sigma (`1.4826 * MAD`, so one ray does not inflate its
  own estimate); a sample is flagged when it exceeds both `threshold` sigma
  (`STACKING_COSMIC_RAY_THRESHOLD`, default 3.0) **and** 12 absolute levels.
- **Combination** (`CombinationService.combine`, honours the reject mask via
  `nan`-aware ops):
  - `median` - robust, default.
  - `mean` - best SNR, only safe with cosmic-ray masking on.
  - `sigma_clip` - 2 iterations of mean +/- 2.5 sigma clipping.

`estimate_snr_improvement(N) = sqrt(N)`.

## Performance notes

| Operation | Typical time (3840x2160) |
|-----------|--------------------------|
| Contrast / brightness / white balance | 5-15 ms |
| Highlights / shadows | 20-30 ms |
| Clarity (unsharp) | 30-50 ms |
| Denoise (bilateral) | 100-300 ms |
| Depth map (Sobel) | 50-100 ms |
| Registration per frame (ORB) | ~0.6 s |
| Registration per frame (SIFT) | ~1.8 s |

Cache intermediate results, vectorize with numpy, and offload heavy jobs to
Celery (phase 2+).
