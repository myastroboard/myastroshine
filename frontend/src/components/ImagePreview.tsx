import { useCallback, useRef, useState, type PointerEvent } from 'react';

import { HistogramDisplay } from '@/components/HistogramDisplay';
import type { HistogramData, StarSourceInfo } from '@/types';

export interface ImagePreviewProps {
  originalUrl: string;
  processedUrl: string;
  histogram?: HistogramData;
  /** Image aspect ratio (width / height); falls back to 16:9. */
  aspectRatio?: number;
  isLoading?: boolean;
  onDepthShiftClick?: () => void;
  /** Detected star circles to draw over the preview, or null to hide the overlay. */
  starMaskOverlay?: StarSourceInfo[] | null;
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
  onDepthShiftClick,
  starMaskOverlay,
}: ImagePreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [splitPercent, setSplitPercent] = useState(50);
  const [dragging, setDragging] = useState(false);
  const [zoom, setZoom] = useState(1);

  const moveSplitTo = useCallback((clientX: number) => {
    const el = containerRef.current;
    if (!el) {
      return;
    }
    const rect = el.getBoundingClientRect();
    const percent = ((clientX - rect.left) / rect.width) * 100;
    setSplitPercent(Math.max(0, Math.min(100, percent)));
  }, []);

  function handlePointerDown(event: PointerEvent<HTMLDivElement>): void {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(true);
    moveSplitTo(event.clientX);
  }

  function handlePointerMove(event: PointerEvent<HTMLDivElement>): void {
    if (dragging) {
      moveSplitTo(event.clientX);
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

  const ratio = aspectRatio && aspectRatio > 0 ? aspectRatio : 16 / 9;
  // Portrait frames would blow past the viewport at full column width; cap their
  // width so the frame stays inside 70vh and centres instead of letterboxing.
  const maxWidth = ratio < 1 ? `calc(70vh * ${ratio})` : '100%';

  return (
    <div className="flex flex-col gap-3">
      <div
        ref={containerRef}
        className="relative mx-auto max-h-[70vh] w-full cursor-ew-resize touch-pan-y select-none overflow-hidden rounded-xl border border-hairline bg-black"
        style={{ aspectRatio: ratio, maxWidth }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        <div
          className="absolute inset-0 origin-center transition-transform duration-100"
          style={{ transform: `scale(${zoom})` }}
        >
          <img
            src={processedUrl}
            alt="Processed"
            draggable={false}
            className="pointer-events-none absolute inset-0 h-full w-full object-contain"
          />
          {/* Same box as the processed image; clip-path reveals only the left split. */}
          <img
            src={originalUrl}
            alt="Original"
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
        </div>

        {/* Divider + grab handle */}
        <div
          className="pointer-events-none absolute inset-y-0 z-10 w-px -translate-x-1/2 bg-white/70 shadow-[0_0_0_1px_rgb(0_0_0/0.35)]"
          style={{ left: `${splitPercent}%` }}
        >
          <span
            className={`absolute left-1/2 top-1/2 flex h-7 w-7 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-white/25 bg-black/60 backdrop-blur-sm transition-transform ${
              dragging ? 'scale-110' : ''
            }`}
          >
            <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 stroke-white/80" fill="none" aria-hidden>
              <path
                d="M6 4 3 8l3 4M10 4l3 4-3 4"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
        </div>

        <div className="pointer-events-none absolute left-3 top-3 rounded bg-black/55 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-white/70 backdrop-blur-sm">
          Before / After
        </div>

        <div
          className="absolute right-3 top-3 flex cursor-default items-center gap-0.5 rounded-md border border-white/10 bg-black/55 p-0.5 text-white/80 backdrop-blur-sm"
          onPointerDown={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            className="grid h-6 w-6 place-items-center rounded transition-colors hover:bg-white/10 disabled:opacity-40"
            aria-label="Zoom out"
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
            aria-label="Reset zoom"
            onClick={() => setZoom(1)}
          >
            {Math.round(zoom * 100)}%
          </button>
          <button
            type="button"
            className="grid h-6 w-6 place-items-center rounded transition-colors hover:bg-white/10 disabled:opacity-40"
            aria-label="Zoom in"
            disabled={zoom >= MAX_ZOOM}
            onClick={() => changeZoom(ZOOM_STEP)}
          >
            <svg viewBox="0 0 12 12" className="h-3 w-3 stroke-current" aria-hidden>
              <path d="M6 2v8M2 6h8" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        {isLoading && (
          <div className="pointer-events-none absolute inset-0 grid place-items-center bg-black/45 backdrop-blur-[1px]">
            <span className="flex items-center gap-2 text-xs font-medium text-white/85">
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/25 border-t-white/80" />
              Processing
            </span>
          </div>
        )}
      </div>

      {histogram && (
        <div className="rounded-lg border border-hairline bg-surface p-3">
          <HistogramDisplay data={histogram} />
        </div>
      )}

      {onDepthShiftClick && (
        <button type="button" className="btn btn-ghost btn-sm self-start" onClick={onDepthShiftClick}>
          Open Depth Shift viewer
        </button>
      )}
    </div>
  );
}
