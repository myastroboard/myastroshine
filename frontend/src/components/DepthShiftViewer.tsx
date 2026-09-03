import { useRef, useState, type MouseEvent } from 'react';

export interface DepthShiftViewerProps {
  depthLayerUrls: string[];
  intensity: number;
  onIntensityChange: (intensity: number) => void;
  onClose: () => void;
}

interface Offset {
  x: number;
  y: number;
}

/**
 * Interactive parallax viewer.
 *
 * Layers translate relative to the pointer; far layers (low index) move most.
 * The per-layer transform is a genuinely dynamic value computed from pointer
 * position, so it stays as an inline style (see AGENTS.md section 5).
 */
export function DepthShiftViewer({
  depthLayerUrls,
  intensity,
  onIntensityChange,
  onClose,
}: DepthShiftViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [offsets, setOffsets] = useState<Offset[]>(depthLayerUrls.map(() => ({ x: 0, y: 0 })));

  function handleMouseMove(event: MouseEvent<HTMLDivElement>): void {
    if (!containerRef.current) {
      return;
    }
    const rect = containerRef.current.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    const y = ((event.clientY - rect.top) / rect.height) * 2 - 1;
    const maxShiftPx = (50 * intensity) / 100;

    setOffsets(
      depthLayerUrls.map((_, index) => {
        const depthFactor = index / depthLayerUrls.length;
        return {
          x: x * maxShiftPx * (1 - depthFactor) * 0.5,
          y: y * maxShiftPx * (1 - depthFactor) * 0.5,
        };
      }),
    );
  }

  return (
    <div
      ref={containerRef}
      className="relative h-[70vh] w-full overflow-hidden rounded-lg bg-black"
      onMouseMove={handleMouseMove}
    >
      {depthLayerUrls.map((url, index) => (
        <img
          key={url}
          src={url}
          alt={`Depth layer ${index}`}
          className="absolute inset-0 h-full w-full object-contain transition-transform duration-75 ease-out"
          style={{ transform: `translate(${offsets[index]?.x ?? 0}px, ${offsets[index]?.y ?? 0}px)` }}
        />
      ))}

      <div className="absolute bottom-4 left-4 rounded bg-black/70 p-3">
        <label className="flex items-center gap-2 text-xs">
          Intensity
          <input
            type="range"
            className="slider-input w-40"
            min={0}
            max={100}
            value={intensity}
            aria-label="Depth shift intensity"
            onChange={(event) => onIntensityChange(Number(event.target.value))}
          />
          <span className="tabular-nums">{intensity}%</span>
        </label>
      </div>

      <button
        type="button"
        className="absolute right-4 top-4 rounded bg-black/70 px-3 py-1 text-sm"
        onClick={onClose}
      >
        Close
      </button>
    </div>
  );
}
