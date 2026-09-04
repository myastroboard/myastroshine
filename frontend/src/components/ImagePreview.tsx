import { useRef, useState, type PointerEvent } from 'react';

import { HistogramDisplay } from '@/components/HistogramDisplay';
import type { HistogramData } from '@/types';

export interface ImagePreviewProps {
  originalUrl: string;
  processedUrl: string;
  histogram?: HistogramData;
  isLoading?: boolean;
  onDepthShiftClick?: () => void;
}

const MIN_ZOOM = 1;
const MAX_ZOOM = 4;
const ZOOM_STEP = 0.5;

/** Before/after split view with a draggable divider and zoom controls. */
export function ImagePreview({
  originalUrl,
  processedUrl,
  histogram,
  isLoading = false,
  onDepthShiftClick,
}: ImagePreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [splitPercent, setSplitPercent] = useState(50);
  const [zoom, setZoom] = useState(1);

  function handlePointerMove(event: PointerEvent<HTMLDivElement>): void {
    if (event.buttons !== 1 || !containerRef.current) {
      return;
    }
    const rect = containerRef.current.getBoundingClientRect();
    const percent = ((event.clientX - rect.left) / rect.width) * 100;
    setSplitPercent(Math.max(0, Math.min(100, percent)));
  }

  function changeZoom(delta: number): void {
    setZoom((current) => {
      const next = Math.round((current + delta) * 100) / 100;
      return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, next));
    });
  }

  return (
    <div className="flex flex-col gap-3">
      <div
        ref={containerRef}
        className="relative aspect-video w-full overflow-hidden rounded-xl border border-hairline bg-black"
        onPointerMove={handlePointerMove}
      >
        <div
          className="absolute inset-0 origin-center transition-transform duration-100"
          style={{ transform: `scale(${zoom})` }}
        >
          <img
            src={processedUrl}
            alt="Processed"
            className="absolute inset-0 h-full w-full object-contain"
          />
          <div className="absolute inset-0 overflow-hidden" style={{ width: `${splitPercent}%` }}>
            <img src={originalUrl} alt="Original" className="h-full w-full object-contain" />
          </div>
          <div
            className="absolute inset-y-0 w-px bg-white/60 shadow-[0_0_0_1px_rgb(0_0_0/0.35)]"
            style={{ left: `${splitPercent}%` }}
          />
        </div>

        <div className="pointer-events-none absolute left-3 top-3 rounded bg-black/55 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-white/70 backdrop-blur-sm">
          Before / After
        </div>

        <div className="absolute right-3 top-3 flex items-center gap-0.5 rounded-md border border-white/10 bg-black/55 p-0.5 text-white/80 backdrop-blur-sm">
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
          <div className="absolute inset-0 grid place-items-center bg-black/45 backdrop-blur-[1px]">
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
        <button
          type="button"
          className="btn btn-ghost btn-sm self-start"
          onClick={onDepthShiftClick}
        >
          Open Depth Shift viewer
        </button>
      )}
    </div>
  );
}
