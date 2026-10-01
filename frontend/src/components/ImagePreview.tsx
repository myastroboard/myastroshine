import { useCallback, useState, type CSSProperties, type PointerEvent, type ReactNode } from 'react';

import { FramingLayer } from '@/components/FramingLayer';
import { HistogramDisplay } from '@/components/HistogramDisplay';
import { ChevronIcon } from '@/components/icons';
import { useTranslation } from '@/hooks/useTranslation';
import { baseAspectRatio } from '@/services/framingGeometry';
import type {
  Dimensions,
  FocusPoint,
  GeometryParameters,
  HistogramData,
  StarSourceInfo,
} from '@/types';

/** When set, the preview shows the crop frame instead of the before/after view. */
export interface FramingState {
  imageUrl: string;
  dimensions: Dimensions;
  geometry: GeometryParameters;
  ratioFrac: number | null;
  onGeometryChange: (next: GeometryParameters) => void;
}

export interface ImagePreviewProps {
  originalUrl: string;
  processedUrl: string;
  histogram?: HistogramData;
  /** Image aspect ratio (width / height); falls back to 16:9. */
  aspectRatio?: number;
  isLoading?: boolean;
  /** 0-100 job progress; a determinate bar shows while it's strictly between. */
  progress?: number;
  /** Overrides the generic "Processing" label under the spinner (e.g. a long pass). */
  progressLabel?: string;
  /** Present only while the Framing step is active. */
  framing?: FramingState | null;
  /** Detected star circles to draw over the preview, or null to hide the overlay. */
  starMaskOverlay?: StarSourceInfo[] | null;
  /** The currently-set Depth Shift focal point, or null/undefined if none. */
  focalPoint?: FocusPoint | null;
  /** While true, a click on the image sets the focal point instead of dragging the divider. */
  pickingFocalPoint?: boolean;
  onFocalPointPick?: (point: FocusPoint) => void;
  /** Rendered under the image, inside the same card (the saved-versions strip). */
  children?: ReactNode;
}

const MIN_ZOOM = 1;
const MAX_ZOOM = 4;
const ZOOM_STEP = 0.5;

/** Before/after split view with a draggable divider and zoom controls. */
export function ImagePreview({
  originalUrl,
  processedUrl,
  histogram,
  aspectRatio,
  isLoading = false,
  progress = 0,
  progressLabel,
  framing,
  starMaskOverlay,
  focalPoint,
  pickingFocalPoint = false,
  onFocalPointPick,
  children,
}: ImagePreviewProps) {
  const { t } = useTranslation();
  const [splitPercent, setSplitPercent] = useState(50);
  const [dragging, setDragging] = useState(false);
  const [zoom, setZoom] = useState(1);
  // Fallback when the caller doesn't know the dimensions (a stacked composite):
  // read them off the processed image once it loads so the frame isn't forced
  // to 16:9 - a portrait composite in a 16:9 box shrinks to a thin strip.
  const [naturalRatio, setNaturalRatio] = useState<number | null>(null);

  // The images sit inside a `scale(zoom)` transform about the centre, so a
  // point at container fraction `f` maps to image fraction `0.5 + (f - 0.5) / zoom`.
  const toImageFraction = useCallback(
    (fraction: number) => 0.5 + (fraction - 0.5) / zoom,
    [zoom],
  );

  const moveSplitTo = useCallback(
    (el: HTMLElement, clientX: number) => {
      const rect = el.getBoundingClientRect();
      const percent = toImageFraction((clientX - rect.left) / rect.width) * 100;
      setSplitPercent(Math.max(0, Math.min(100, percent)));
    },
    [toImageFraction],
  );

  function handlePointerDown(event: PointerEvent<HTMLDivElement>): void {
    if (pickingFocalPoint) {
      const rect = event.currentTarget.getBoundingClientRect();
      onFocalPointPick?.({
        x: Math.max(0, Math.min(1, toImageFraction((event.clientX - rect.left) / rect.width))),
        y: Math.max(0, Math.min(1, toImageFraction((event.clientY - rect.top) / rect.height))),
      });
      return;
    }
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(true);
    moveSplitTo(event.currentTarget, event.clientX);
  }

  function handlePointerMove(event: PointerEvent<HTMLDivElement>): void {
    if (dragging) {
      moveSplitTo(event.currentTarget, event.clientX);
    }
  }

  function endDrag(event: PointerEvent<HTMLDivElement>): void {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    setDragging(false);
  }

  function changeZoom(delta: number): void {
    setZoom((current) => {
      const next = Math.round((current + delta) * 100) / 100;
      return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, next));
    });
  }

  const framingActive = Boolean(framing);
  const ratio = framing
    ? baseAspectRatio(framing.dimensions, framing.geometry.rotateQuarters)
    : aspectRatio && aspectRatio > 0
      ? aspectRatio
      : naturalRatio && naturalRatio > 0
        ? naturalRatio
        : 16 / 9;
  // Portrait frames would blow past the viewport at full column width; cap their
  // width so the frame stays inside its max height (70vh, 42vh on a phone where
  // the preview is pinned above the controls) and centres instead of letterboxing.
  const frameStyle = { aspectRatio: ratio, '--frame-ratio': ratio } as CSSProperties;
  const portrait = ratio < 1;
  // Hide a side's label once the divider has nearly swept it off-screen.
  const showBefore = splitPercent > 12;
  const showAfter = splitPercent < 88;

  return (
    <div className="panel flex flex-col gap-3">
      <div
        className={`relative mx-auto max-h-[42vh] w-full touch-pan-y select-none overflow-hidden rounded-lg border border-hairline bg-black lg:max-h-[70vh] ${
          portrait ? 'max-w-[calc(42vh*var(--frame-ratio))] lg:max-w-[calc(70vh*var(--frame-ratio))]' : ''
        } ${framingActive ? '' : pickingFocalPoint ? 'cursor-crosshair' : 'cursor-ew-resize'}`}
        style={frameStyle}
        onPointerDown={framingActive ? undefined : handlePointerDown}
        onPointerMove={framingActive ? undefined : handlePointerMove}
        onPointerUp={framingActive ? undefined : endDrag}
        onPointerCancel={framingActive ? undefined : endDrag}
      >
        {framing ? (
          <FramingLayer
            imageUrl={framing.imageUrl}
            dimensions={framing.dimensions}
            geometry={framing.geometry}
            ratioFrac={framing.ratioFrac}
            onGeometryChange={framing.onGeometryChange}
          />
        ) : (
          <>
            <div
              className="absolute inset-0 origin-center transition-transform duration-100"
              style={{ transform: `scale(${zoom})` }}
            >
              <img
                src={processedUrl}
                alt={t('image_preview.processed_alt')}
                draggable={false}
                className="pointer-events-none absolute inset-0 h-full w-full object-contain"
                onLoad={(event) => {
                  const { naturalWidth, naturalHeight } = event.currentTarget;
                  if (naturalWidth > 0 && naturalHeight > 0) {
                    setNaturalRatio(naturalWidth / naturalHeight);
                  }
                }}
              />
              {/* Same box as the processed image; clip-path reveals only the left split. */}
              <img
                src={originalUrl}
                alt={t('image_preview.original_alt')}
                draggable={false}
                className="pointer-events-none absolute inset-0 h-full w-full object-contain"
                style={{ clipPath: `inset(0 ${100 - splitPercent}% 0 0)` }}
              />
              {starMaskOverlay && starMaskOverlay.length > 0 && (
                // viewBox width:height matches the container's own aspect ratio, so
                // the (non-uniform in general) preserveAspectRatio="none" stretch is
                // actually uniform here - circles stay round. See radius conversion
                // below: a longest-side fraction needs `* max(ratio, 1)` to land in
                // these viewBox units.
                <svg
                  viewBox={`0 0 ${ratio} 1`}
                  preserveAspectRatio="none"
                  className="pointer-events-none absolute inset-0 h-full w-full stroke-accent"
                  fill="none"
                  aria-hidden
                >
                  {starMaskOverlay.map((star, index) => (
                    <circle
                      key={index}
                      cx={star.x * ratio}
                      cy={star.y}
                      r={Math.max(star.radius * Math.max(ratio, 1), 0.006)}
                      strokeWidth={0.006}
                      opacity={0.85}
                    />
                  ))}
                </svg>
              )}
              {focalPoint && (
                <div
                  className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2"
                  style={{ left: `${focalPoint.x * 100}%`, top: `${focalPoint.y * 100}%` }}
                >
                  <svg viewBox="0 0 24 24" className="h-6 w-6 stroke-accent" fill="none" aria-hidden>
                    <circle cx="12" cy="12" r="7" strokeWidth="1.5" />
                    <path
                      d="M12 2v4M12 18v4M2 12h4M18 12h4"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                    />
                  </svg>
                </div>
              )}
            </div>

            {pickingFocalPoint && (
              <div className="pointer-events-none absolute inset-x-0 top-3 z-10 mx-auto w-fit rounded bg-black/70 px-3 py-1 text-xs font-medium text-white/90 backdrop-blur-sm">
                {t('image_preview.click_to_set_focal_point')}
              </div>
            )}

            {/* Divider + grab handle. The images are zoomed about the centre, so
                the clip edge (splitPercent of the image) lands at this fraction
                of the unscaled container. */}
            <div
              className="pointer-events-none absolute inset-y-0 z-10 w-0.5 -translate-x-1/2 bg-white/80 shadow-[0_0_0_1px_rgb(0_0_0/0.35)]"
              style={{ left: `${50 + (splitPercent - 50) * zoom}%` }}
            >
              <span
                className={`absolute left-1/2 top-1/2 flex h-10 w-10 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-white/30 bg-black/60 shadow-lg backdrop-blur-sm transition-transform ${
                  dragging ? 'scale-110' : ''
                }`}
              >
                <svg
                  viewBox="0 0 16 16"
                  className="h-4 w-4 stroke-white/90"
                  fill="none"
                  aria-hidden
                >
                  <path
                    d="M6 4 3 8l3 4M10 4l3 4-3 4"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </span>
            </div>

            {/* Which side is which - on the image, so it reads without a legend. */}
            {showBefore && (
              <div className="pointer-events-none absolute bottom-3 left-3 rounded-md bg-black/55 px-2.5 py-1 text-xs font-medium text-white/85 backdrop-blur-sm">
                {t('image_preview.before')}
              </div>
            )}
            {showAfter && (
              <div className="pointer-events-none absolute bottom-3 right-3 rounded-md bg-black/55 px-2.5 py-1 text-xs font-medium text-white/85 backdrop-blur-sm">
                {t('image_preview.after')}
              </div>
            )}

            <div
              className="absolute right-3 top-3 flex cursor-default items-center gap-0.5 rounded-md border border-white/10 bg-black/55 p-0.5 text-white/80 backdrop-blur-sm"
              onPointerDown={(event) => event.stopPropagation()}
            >
              <button
                type="button"
                className="grid h-6 w-6 place-items-center rounded transition-colors hover:bg-white/10 disabled:opacity-40"
                aria-label={t('image_preview.zoom_out')}
                disabled={zoom <= MIN_ZOOM}
                onClick={() => changeZoom(-ZOOM_STEP)}
              >
                <svg viewBox="0 0 12 12" className="h-3 w-3 stroke-current" aria-hidden>
                  <path d="M2 6h8" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
              <button
                type="button"
                className="min-w-[3rem] rounded px-1 py-1 text-xs tabular-nums transition-colors hover:bg-white/10"
                aria-label={t('image_preview.reset_zoom')}
                onClick={() => setZoom(1)}
              >
                {Math.round(zoom * 100)}%
              </button>
              <button
                type="button"
                className="grid h-6 w-6 place-items-center rounded transition-colors hover:bg-white/10 disabled:opacity-40"
                aria-label={t('image_preview.zoom_in')}
                disabled={zoom >= MAX_ZOOM}
                onClick={() => changeZoom(ZOOM_STEP)}
              >
                <svg viewBox="0 0 12 12" className="h-3 w-3 stroke-current" aria-hidden>
                  <path d="M6 2v8M2 6h8" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
            </div>
          </>
        )}

        {isLoading && (
          <div className="pointer-events-none absolute inset-0 grid place-items-center bg-black/45 backdrop-blur-[1px]">
            <div className="flex w-40 flex-col items-center gap-2 text-xs font-medium text-white/85">
              <span className="flex items-center gap-2">
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/25 border-t-white/80" />
                {progressLabel ?? t('image_preview.processing')}
              </span>
              {progress > 0 && progress < 100 && (
                <span
                  role="progressbar"
                  aria-valuenow={Math.round(progress)}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  className="h-1 w-full overflow-hidden rounded-full bg-white/20"
                >
                  <span
                    className="block h-full rounded-full bg-white/80 transition-[width] duration-300"
                    style={{ width: `${progress}%` }}
                  />
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {children}

      {histogram && (
        // Folded by default: useful to a few, noise to most - and kept out of
        // the pinned phone preview entirely.
        <details className="group max-lg:hidden">
          <summary className="flex w-fit cursor-pointer list-none items-center gap-1 text-xs font-medium text-faint outline-none hover:text-muted focus-visible:ring-2 focus-visible:ring-accent [&::-webkit-details-marker]:hidden">
            <ChevronIcon className="h-3 w-3 transition-transform group-open:rotate-90" />
            {t('histogram.toggle')}
          </summary>
          <div className="panel-inset mt-2">
            <HistogramDisplay data={histogram} />
          </div>
        </details>
      )}
    </div>
  );
}
