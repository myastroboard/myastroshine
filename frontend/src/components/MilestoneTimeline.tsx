import { BookmarkIcon, HistoryIcon } from '@/components/icons';
import { useTranslation } from '@/hooks/useTranslation';
import type { Milestone } from '@/hooks/useMilestones';
import { EDITOR_STEPS, stepChanged } from '@/types';

/** How many step names a chip spells out before trailing off. */
const NAMED_STEPS = 2;

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
 * The go-back points under the preview. Each chip restores that snapshot of the
 * adjustments and is named after what changed since the previous point
 * ("2 - Light, Colour"), so the list reads as a history rather than a row of
 * anonymous numbers; "Mark this point" captures the current state. There is no
 * delete - a new image clears the list. Rendered inside the preview card, right
 * where the user judges the result.
 */
export function MilestoneTimeline({
  milestones,
  activeId,
  onCapture,
  onRestore,
  disabled = false,
}: MilestoneTimelineProps) {
  const { t } = useTranslation();

  /** The chip text (short) and its full form (tooltip and screen readers). */
  const labels = (milestone: Milestone, index: number): { short: string; full: string } => {
    if (milestone.kind === 'origin' || index === 0) {
      const origin = t('editor.milestones.origin');
      return { short: origin, full: origin };
    }
    const previous = milestones[index - 1];
    const changed = EDITOR_STEPS.filter((step) =>
      stepChanged(step, previous.parameters, milestone.parameters, previous.focalPoint, milestone.focalPoint),
    ).map((step) => t(`editor.rail.${step.id}`));
    if (changed.length === 0) {
      const plain = t('editor.milestones.point', { n: milestone.ordinal });
      return { short: plain, full: plain };
    }
    const named = changed.slice(0, NAMED_STEPS).join(', ');
    return {
      short: t('editor.milestones.point_named', {
        n: milestone.ordinal,
        steps: changed.length > NAMED_STEPS ? `${named}, ...` : named,
      }),
      full: t('editor.milestones.point_named', { n: milestone.ordinal, steps: changed.join(', ') }),
    };
  };

  const last = milestones[milestones.length - 1];
  // Right after "Mark this point" the newest point is the live state: say so,
  // and how to use it. Otherwise restate what the feature is for.
  const justSaved = last.kind === 'saved' && last.id === activeId;
  // Edits that no point holds yet: nudge towards marking one.
  const unsaved = activeId === null;

  return (
    <div className="flex flex-col gap-2 border-t border-hairline pt-3">
      <div className="flex items-start justify-between gap-3">
        <span className="flex min-w-0 items-start gap-2">
          <HistoryIcon className="mt-0.5 h-4 w-4 text-accent" />
          <span className="flex min-w-0 flex-col">
            <span className="text-sm font-medium text-ink">{t('editor.milestones.title')}</span>
            {/* On a phone the pinned preview is tight: keep the explanation
                for when it helps - before the first point, or just after one. */}
            <span
              className={`text-xs text-faint ${milestones.length > 1 && !justSaved ? 'max-lg:hidden' : ''}`}
              aria-live="polite"
            >
              {justSaved
                ? t('editor.milestones.saved', { n: last.ordinal })
                : t('editor.milestones.help')}
            </span>
          </span>
        </span>
        <button
          type="button"
          className={`btn btn-outline btn-sm shrink-0 ${
            unsaved ? 'border-accent/60 bg-accent-wash text-accent' : ''
          }`}
          disabled={disabled}
          onClick={onCapture}
        >
          <BookmarkIcon className="h-3.5 w-3.5" />
          <span className="max-sm:sr-only">{t('editor.milestones.add')}</span>
        </button>
      </div>
      <div className="flex gap-1.5 overflow-x-auto py-0.5">
        {milestones.map((milestone, index) => {
          const active = milestone.id === activeId;
          const label = labels(milestone, index);
          return (
            <button
              key={milestone.id}
              type="button"
              className={`chip shrink-0 px-2.5 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-40 ${
                active ? 'chip-active' : ''
              }`}
              aria-pressed={active}
              aria-label={t('editor.milestones.restore_aria', { label: label.full })}
              title={label.full}
              disabled={disabled}
              onClick={() => onRestore(milestone)}
            >
              {label.short}
            </button>
          );
        })}
      </div>
    </div>
  );
}
