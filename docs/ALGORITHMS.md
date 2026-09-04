# Processing algorithms

Reference for the image processing pipeline. Implementations live in
`app/services/image_processing.py`, `app/services/depth_map.py`, and the stacking
services. All functions operate on BGR `uint8` numpy arrays unless noted.

## Single-image pipeline

Applied in this order to minimize artifacts (`apply_parameters`):

1. **White balance** (`temperature`, `tint`) - per-channel gain in linear RGB;
   6500K is neutral. Warm shifts reduce blue, cool shifts boost blue.
2. **Contrast** (`contrast`, 0.5-3.0) - linear scaling around the image mean,
   `y = (x - mean) * contrast + mean`, then a mild gamma for a smooth response.
3. **Brightness** (`brightness`, -1..1) - pixel offset, `beta = brightness * 50`.
4. **Highlights / shadows** (-1..1) - masked tone curves; `gray^2` emphasizes
   bright regions, `(1 - gray)^2` emphasizes dark regions, scaled by 0.3.
5. **Saturation** (0-2) - scale the HSV S channel.
6. **Vibrance** (0-2) - saturation boost weighted by `(1 - current_saturation)`
   so already-saturated pixels move less.
7. **Clarity** (-1..1) - unsharp mask against a 21x21 Gaussian blur; positive
   sharpens, negative softens.
8. **Denoise** (0-100) - bilateral filter; map to diameter 5-20 and
   sigma_color / sigma_space 75-150. Above 50, add a 3x3 morphological close.
9. **Sharpness** (0-2) - below 1.0 Gaussian blur, above 1.0 Laplacian-kernel
   sharpen blended by `(sharpness - 1) * 0.5`.

Preview path downscales to 512 px (`preview_max_size`) for instant feedback; the
full-resolution result is computed on demand or via the job queue.

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
