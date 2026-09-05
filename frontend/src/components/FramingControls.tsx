import { useTranslation } from '@/hooks/useTranslation';
import { RATIOS, baseAspectRatio, rectForRatio } from '@/services/framingGeometry';
import type { Dimensions, GeometryParameters } from '@/types';

export interface FramingControlsProps {
  /** Original (unrotated) image dimensions. */
  dimensions: Dimensions;
  /** The working (uncommitted) framing. */
  geometry: GeometryParameters;
  /** Resize ratio lock, shared with the on-image handle layer. */
  ratioFrac: number | null;
  /** True when the working framing differs from what is currently applied. */
  dirty: boolean;
  onGeometryChange: (next: GeometryParameters) => void;
  onRatioFracChange: (next: number | null) => void;
  onApply: () => void;
  onReset: () => void;
  isProcessing?: boolean;
}

/** Step 1 inspector: aspect ratio, straighten, rotate and flip. The crop
 * rectangle itself is dragged on the main preview (`FramingLayer`). */
export function FramingControls({
  dimensions,
  geometry,
  ratioFrac,
  dirty,
  onGeometryChange,
  onRatioFracChange,
  onApply,
  onReset,
  isProcessing = false,
}: FramingControlsProps) {
  const { t } = useTranslation();
  const baseAspect = baseAspectRatio(dimensions, geometry.rotateQuarters);

  function chooseRatio(displayRatio: number | null): void {
    const { ratioFrac: nextFrac, rect } = rectForRatio(displayRatio, baseAspect);
    onRatioFracChange(nextFrac);
    if (rect) {
      onGeometryChange({ ...geometry, cropX: rect.x, cropY: rect.y, cropW: rect.w, cropH: rect.h });
    }
  }

  function rotate90(): void {
    onRatioFracChange(null);
    onGeometryChange({
      ...geometry,
      rotateQuarters: (geometry.rotateQuarters + 1) % 4,
      cropX: 0,
      cropY: 0,
      cropW: 1,
      cropH: 1,
    });
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-1.5">
        {RATIOS.map((r) => {
          const fr = r.value === null ? null : (r.value || baseAspect) / baseAspect;
          const active =
            fr === null
              ? ratioFrac === null
              : ratioFrac !== null && Math.abs(ratioFrac - fr) < 0.001;
          return (
            <button
              key={r.label}
              type="button"
              className={`chip ${active ? 'chip-active' : ''}`}
              aria-pressed={active}
              disabled={isProcessing}
              onClick={() => chooseRatio(r.value)}
            >
              {r.translationKey ? t(r.translationKey) : r.label}
            </button>
          );
        })}
      </div>

      <label className="flex items-center gap-3 text-xs">
        <span className="w-16 uppercase tracking-wide text-faint">
          {t('crop_tool.straighten_label')}
        </span>
        <input
          type="range"
          className="slider flex-1"
          min={-45}
          max={45}
          step={0.1}
          value={geometry.straighten}
          disabled={isProcessing}
          aria-label={t('crop_tool.straighten_label')}
          onChange={(e) => onGeometryChange({ ...geometry, straighten: Number(e.target.value) })}
        />
        <span className="w-11 text-right tabular-nums">{geometry.straighten.toFixed(1)}&deg;</span>
      </label>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn btn-outline btn-sm"
          disabled={isProcessing}
          onClick={rotate90}
        >
          {t('crop_tool.rotate_90')}
        </button>
        <button
          type="button"
          className={`btn btn-sm ${geometry.flipHorizontal ? 'btn-primary' : 'btn-outline'}`}
          aria-pressed={geometry.flipHorizontal}
          disabled={isProcessing}
          onClick={() =>
            onGeometryChange({
              ...geometry,
              flipHorizontal: !geometry.flipHorizontal,
              cropX: 1 - geometry.cropX - geometry.cropW,
            })
          }
        >
          {t('crop_tool.flip_h')}
        </button>
        <button
          type="button"
          className={`btn btn-sm ${geometry.flipVertical ? 'btn-primary' : 'btn-outline'}`}
          aria-pressed={geometry.flipVertical}
          disabled={isProcessing}
          onClick={() =>
            onGeometryChange({
              ...geometry,
              flipVertical: !geometry.flipVertical,
              cropY: 1 - geometry.cropY - geometry.cropH,
            })
          }
        >
          {t('crop_tool.flip_v')}
        </button>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          className="btn btn-primary btn-sm"
          disabled={isProcessing || !dirty}
          onClick={onApply}
        >
          {t('crop_tool.apply')}
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          disabled={isProcessing}
          onClick={() => {
            onRatioFracChange(null);
            onReset();
          }}
        >
          {t('common.reset')}
        </button>
      </div>
    </div>
  );
}
