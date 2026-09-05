import { useEffect, useRef, useState, type MouseEvent } from 'react';

import { useTranslation } from '@/hooks/useTranslation';

export interface DepthShiftViewerProps {
  depthLayerUrls: string[];
  intensity: number;
  /** Image aspect ratio (width / height); falls back to 16:9. */
  aspectRatio?: number;
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
  aspectRatio,
  onIntensityChange,
  onClose,
}: DepthShiftViewerProps) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const [offsets, setOffsets] = useState<Offset[]>(depthLayerUrls.map(() => ({ x: 0, y: 0 })));

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

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
      className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={t('depth_shift_viewer.dialog_aria_label')}
      onClick={(event) => event.target === event.currentTarget && onClose()}
    >
      <div
        ref={containerRef}
        className="relative max-h-[85vh] w-full max-w-5xl overflow-hidden rounded-xl border border-line bg-black shadow-pop"
        style={{
          aspectRatio: aspectRatio && aspectRatio > 0 ? aspectRatio : 16 / 9,
          maxWidth: aspectRatio && aspectRatio < 1 ? `calc(85vh * ${aspectRatio})` : undefined,
        }}
        onMouseMove={handleMouseMove}
      >
        {depthLayerUrls.map((url, index) => (
          <img
            key={url}
            src={url}
            alt={t('depth_shift_viewer.layer_alt', { index })}
            className="absolute inset-0 h-full w-full object-contain transition-transform duration-75 ease-out"
            style={{
              transform: `translate(${offsets[index]?.x ?? 0}px, ${offsets[index]?.y ?? 0}px)`,
            }}
          />
        ))}

        <div className="absolute bottom-4 left-4 flex items-center gap-3 rounded-lg border border-white/10 bg-black/60 px-3 py-2 text-xs text-white/85 backdrop-blur-sm">
          <span className="uppercase tracking-wide text-white/60">
            {t('depth_shift_viewer.intensity_label')}
          </span>
          <input
            type="range"
            className="slider w-40"
            min={0}
            max={100}
            value={intensity}
            aria-label={t('depth_shift_viewer.intensity_aria_label')}
            onChange={(event) => onIntensityChange(Number(event.target.value))}
          />
          <span className="w-9 text-right tabular-nums">{intensity}%</span>
        </div>

        <button
          type="button"
          className="absolute right-4 top-4 rounded-md border border-white/10 bg-black/60 px-3 py-1.5 text-sm text-white/85 backdrop-blur-sm transition-colors hover:bg-black/80"
          onClick={onClose}
        >
          {t('depth_shift_viewer.close')}
        </button>
      </div>
    </div>
  );
}
