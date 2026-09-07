import { useTranslation } from '@/hooks/useTranslation';
import type { Milestone } from '@/hooks/useMilestones';

export interface MilestoneTimelineProps {
  milestones: Milestone[];
  /** Milestone whose snapshot matches the current edit state, or null. */
  activeId: string | null;
  onCapture: () => void;
  onRestore: (milestone: Milestone) => void;
  /** Disable interaction while a processing job is in flight. */
  disabled?: boolean;
}

/**
 * Horizontal timeline of in-memory edit milestones. Each marker restores that
 * snapshot of the adjustments; "+" captures the current state as a new one.
 * There is no delete - a new image clears the timeline.
 */
export function MilestoneTimeline({
  milestones,
  activeId,
  onCapture,
  onRestore,
  disabled = false,
}: MilestoneTimelineProps) {
  const { t } = useTranslation();

  const label = (milestone: Milestone) =>
    milestone.kind === 'origin'
      ? t('editor.milestones.origin')
      : t('editor.milestones.point', { n: milestone.ordinal });

  return (
    <div className="panel flex flex-col gap-3">
      <h2 className="eyebrow">{t('editor.milestones.title')}</h2>

      <div className="flex items-center gap-3">
        <div className="relative min-w-0 flex-1 overflow-x-auto">
          <div className="pointer-events-none absolute inset-x-1 top-1/2 h-px -translate-y-1/2 bg-line" />
          <div className="relative flex items-center gap-4 py-1">
            {milestones.map((milestone) => {
              const active = milestone.id === activeId;
              return (
                <button
                  key={milestone.id}
                  type="button"
                  className="group shrink-0 rounded-sm p-1 outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-40"
                  aria-pressed={active}
                  aria-label={t('editor.milestones.restore_aria', { label: label(milestone) })}
                  title={label(milestone)}
                  disabled={disabled}
                  onClick={() => onRestore(milestone)}
                >
                  <svg viewBox="0 0 12 12" className="h-3 w-3" aria-hidden>
                    <path
                      d="M6 1.5 11 10.5H1z"
                      className={
                        active ? 'fill-accent' : 'fill-line-strong group-hover:fill-muted'
                      }
                    />
                  </svg>
                </button>
              );
            })}
          </div>
        </div>

        <button
          type="button"
          className="btn btn-outline btn-sm shrink-0"
          aria-label={t('editor.milestones.add')}
          title={t('editor.milestones.add')}
          disabled={disabled}
          onClick={onCapture}
        >
          <svg viewBox="0 0 12 12" className="h-3 w-3 stroke-current" fill="none" aria-hidden>
            <path d="M6 2v8M2 6h8" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      <p className="text-xs text-faint">{t('editor.milestones.help')}</p>
    </div>
  );
}
