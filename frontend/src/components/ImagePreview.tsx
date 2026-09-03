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

/** Before/after split view with a draggable divider. */
export function ImagePreview({
  originalUrl,
  processedUrl,
  histogram,
  isLoading = false,
  onDepthShiftClick,
}: ImagePreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [splitPercent, setSplitPercent] = useState(50);

  function handlePointerMove(event: PointerEvent<HTMLDivElement>): void {
    if (event.buttons !== 1 || !containerRef.current) {
      return;
    }
    const rect = containerRef.current.getBoundingClientRect();
    const percent = ((event.clientX - rect.left) / rect.width) * 100;
    setSplitPercent(Math.max(0, Math.min(100, percent)));
  }

  return (
    <div className="flex flex-col gap-3">
      <div
        ref={containerRef}
        className="relative aspect-video w-full overflow-hidden rounded-lg bg-black"
        onPointerMove={handlePointerMove}
      >
        <img src={processedUrl} alt="Processed" className="absolute inset-0 h-full w-full object-contain" />
        <div className="absolute inset-0 overflow-hidden" style={{ width: `${splitPercent}%` }}>
          <img src={originalUrl} alt="Original" className="h-full w-full object-contain" />
        </div>
        <div className="absolute inset-y-0 w-0.5 bg-white/70" style={{ left: `${splitPercent}%` }} />
        {isLoading && (
          <div className="absolute inset-0 grid place-items-center bg-black/40 text-sm">Processing...</div>
        )}
      </div>

      {histogram && <HistogramDisplay data={histogram} />}

      {onDepthShiftClick && (
        <button type="button" className="self-start text-xs text-secondary underline" onClick={onDepthShiftClick}>
          Open Depth Shift viewer
        </button>
      )}
    </div>
  );
}
