import { useTranslation } from '@/hooks/useTranslation';
import type { PendingFrame } from '@/hooks/useStackProcessing';
import type { StackFrameInfo } from '@/types';

export interface StackFrameGridProps {
  pending: PendingFrame[];
  uploaded: StackFrameInfo[];
  selected: number | null;
  interactive: boolean;
  onRemovePending: (id: string) => void;
  onSelect: (index: number) => void;
  onToggleExclude: (index: number, excluded: boolean) => void;
}

/** The frame panel: pending files as name chips, then uploaded frames as a
 * thumbnail grid where each tile can be previewed and excluded. */
export function StackFrameGrid({
  pending,
  uploaded,
  selected,
  interactive,
  onRemovePending,
  onSelect,
  onToggleExclude,
}: StackFrameGridProps) {
  const { t } = useTranslation();

  if (pending.length === 0 && uploaded.length === 0) {
    return null;
  }

  return (
    <div className="panel flex flex-col gap-3">
      {uploaded.length > 0 && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(84px,1fr))] gap-2">
          {uploaded.map((frame) => {
            const isSelected = frame.index === selected;
            const q = frame.quality;
            const autoRejected = q != null && !q.accepted;
            return (
              <div key={frame.index} className="relative">
                <button
                  type="button"
                  onClick={() => onSelect(frame.index)}
                  aria-pressed={isSelected}
                  aria-label={t('stacking.grid.frame_aria', { n: frame.index + 1 })}
                  className={`block w-full overflow-hidden rounded-md border ${
                    isSelected
                      ? 'border-accent ring-1 ring-accent'
                      : autoRejected
                        ? 'border-danger/60'
                        : 'border-hairline'
                  }`}
                >
                  <img
                    src={frame.thumbUrl}
                    alt=""
                    loading="lazy"
                    className={`aspect-square w-full bg-black object-cover ${
                      frame.excluded ? 'opacity-40 grayscale' : ''
                    }`}
                  />
                </button>

                {q != null && (
                  <span
                    className={`pointer-events-none absolute bottom-1 left-1 rounded px-1 text-[10px] font-medium tabular-nums ${
                      autoRejected ? 'bg-danger/80 text-white' : 'bg-black/60 text-white/90'
                    }`}
                    title={
                      autoRejected
                        ? t(`stacking.grid.reject.${q.rejectReason ?? 'other'}`)
                        : t('stacking.grid.quality_title', {
                            stars: q.starCount,
                            fwhm: q.fwhm.toFixed(1),
                          })
                    }
                  >
                    {autoRejected
                      ? t(`stacking.grid.reject.${q.rejectReason ?? 'other'}`)
                      : Math.round(q.score)}
                  </span>
                )}

                <label
                  className="absolute right-1 top-1 flex cursor-pointer items-center rounded bg-black/60 p-0.5"
                  title={t('stacking.grid.exclude')}
                >
                  <input
                    type="checkbox"
                    className="size-3.5 accent-danger"
                    checked={frame.excluded}
                    disabled={!interactive}
                    onChange={(event) => onToggleExclude(frame.index, event.target.checked)}
                  />
                </label>
              </div>
            );
          })}
        </div>
      )}

      {pending.length > 0 && (
        <ul className="panel-inset flex flex-col divide-y divide-hairline px-3 py-0 text-xs">
          {pending.map((frame) => (
            <li key={frame.id} className="flex items-center justify-between gap-3 py-2">
              <span className="truncate text-muted">{frame.name}</span>
              <button
                type="button"
                onClick={() => onRemovePending(frame.id)}
                className="shrink-0 text-faint hover:text-danger"
                aria-label={t('stacking.grid.remove', { name: frame.name })}
              >
                <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 stroke-current" fill="none" aria-hidden>
                  <path d="M6 6l12 12M18 6L6 18" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
