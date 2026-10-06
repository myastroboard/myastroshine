import { useEffect, useRef, type ComponentType } from 'react';

import {
  CropIcon,
  CurveIcon,
  DepthIcon,
  DownloadIcon,
  FocusIcon,
  LayersIcon,
  PaletteIcon,
  SkyIcon,
  SparkleIcon,
  StarIcon,
  SunIcon,
  WandIcon,
  type IconProps,
} from '@/components/icons';
import { useTranslation } from '@/hooks/useTranslation';
import {
  editorStepsFor,
  stepIsModified,
  type EditorPhase,
  type EditorStepId,
  type FocusPoint,
  type ProcessingParameters,
} from '@/types';

/** Phases that get a heading in the desktop rail; the start and export
 * brackets around them are set off by a hairline instead. */
const TITLED_PHASES = new Set<EditorPhase>(['prepare', 'enhance', 'finish']);

/** One icon per workflow step - the rail and the mobile tab bar show these. */
export const STEP_ICONS: Record<EditorStepId, ComponentType<IconProps>> = {
  stack: LayersIcon,
  start: SparkleIcon,
  frame: CropIcon,
  sky: SkyIcon,
  light: SunIcon,
  curves: CurveIcon,
  colour: PaletteIcon,
  detail: FocusIcon,
  stars: StarIcon,
  depth: DepthIcon,
  style: WandIcon,
  export: DownloadIcon,
};

export interface EditorRailProps {
  activeStep: EditorStepId;
  onStepChange: (step: EditorStepId) => void;
  parameters: ProcessingParameters;
  focalPoint: FocusPoint | null;
  /** Show the composite-only "Stack" step. */
  isStack: boolean;
}

/**
 * The workflow rail: pick which group of tools the inspector shows. On desktop
 * a vertical list grouped by phase, each step with a plain-language subtitle;
 * below `lg` a tab bar pinned to the bottom of the screen (icon over label),
 * so the controls and the preview keep the whole viewport.
 */
export function EditorRail({
  activeStep,
  onStepChange,
  parameters,
  focalPoint,
  isStack,
}: EditorRailProps) {
  const { t } = useTranslation();
  const activeRef = useRef<HTMLButtonElement>(null);

  // The phone tab bar scrolls sideways: keep the active step in view when it
  // changes (the "Next step" button can land on one that is off-screen).
  // Phone layout only: on desktop the vertical rail must not yank the page.
  useEffect(() => {
    if (window.matchMedia?.('(max-width: 1023.98px)').matches) {
      activeRef.current?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
    }
  }, [activeStep]);

  return (
    <nav
      aria-label={t('editor.rail.aria_label')}
      className="max-lg:fixed max-lg:inset-x-0 max-lg:bottom-0 max-lg:z-30 max-lg:flex max-lg:gap-0.5 max-lg:overflow-x-auto max-lg:border-t max-lg:border-hairline max-lg:bg-canvas/95 max-lg:px-2 max-lg:py-1.5 max-lg:backdrop-blur-md lg:flex lg:flex-col lg:gap-0.5"
    >
      {editorStepsFor(isStack).map((step, index, steps) => {
        const active = step.id === activeStep;
        const modified = stepIsModified(step, parameters, focalPoint);
        const Icon = STEP_ICONS[step.id];
        const newPhase = index === 0 || steps[index - 1].phase !== step.phase;
        const hintId = `rail-hint-${step.id}`;
        return (
          <div key={step.id} className="contents">
            {newPhase && index > 0 && TITLED_PHASES.has(step.phase) && (
              <span className="eyebrow hidden px-2.5 pb-1 pt-3 lg:block" aria-hidden>
                {t(`editor.rail.phase.${step.phase}`)}
              </span>
            )}
            {newPhase && index > 0 && !TITLED_PHASES.has(step.phase) && (
              <span className="hidden lg:my-2 lg:block lg:border-t lg:border-hairline" aria-hidden />
            )}
            <button
              type="button"
              ref={active ? activeRef : undefined}
              aria-current={active ? 'step' : undefined}
              aria-describedby={hintId}
              onClick={() => onStepChange(step.id)}
              className={`group relative flex shrink-0 rounded-md text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-accent max-lg:min-w-[4.25rem] max-lg:flex-col max-lg:items-center max-lg:gap-1 max-lg:px-1.5 max-lg:py-1.5 lg:w-full lg:items-start lg:gap-2.5 lg:px-2.5 lg:py-2 ${
                active ? 'bg-accent-wash text-ink' : 'text-muted hover:bg-hover hover:text-ink'
              }`}
            >
              <Icon
                className={`h-[1.125rem] w-[1.125rem] lg:mt-px ${
                  active ? 'text-accent' : 'text-faint group-hover:text-muted'
                }`}
              />
              <span className="flex min-w-0 flex-1 flex-col max-lg:items-center">
                <span className="truncate text-sm max-lg:text-[11px] max-lg:leading-tight">
                  {t(`editor.rail.${step.id}`)}
                </span>
                <span id={hintId} aria-hidden className="text-[11px] leading-snug text-faint max-lg:sr-only">
                  {t(`editor.rail.hint.${step.id}`)}
                </span>
              </span>
              {modified && (
                <span
                  className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent max-lg:absolute max-lg:right-2 max-lg:top-1.5 lg:mt-2"
                  aria-label={t('editor.rail.modified')}
                />
              )}
            </button>
          </div>
        );
      })}
    </nav>
  );
}
