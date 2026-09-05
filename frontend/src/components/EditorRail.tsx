import { useTranslation } from '@/hooks/useTranslation';
import {
  DEFAULT_PARAMETERS,
  EDITOR_STEPS,
  isDefaultGeometry,
  type EditorStep,
  type EditorStepId,
  type FocusPoint,
  type ProcessingParameters,
} from '@/types';

export interface EditorRailProps {
  activeStep: EditorStepId;
  onStepChange: (step: EditorStepId) => void;
  parameters: ProcessingParameters;
  focalPoint: FocusPoint | null;
}

/** True when a step's controls hold a value that differs from the default. */
function stepIsModified(
  step: EditorStep,
  parameters: ProcessingParameters,
  focalPoint: FocusPoint | null,
): boolean {
  switch (step.id) {
    case 'start':
    case 'export':
      return false;
    case 'frame':
      return !isDefaultGeometry(parameters.geometry);
    case 'curves':
      return (
        parameters.curvePoints.length > 0 ||
        parameters.redCurvePoints.length > 0 ||
        parameters.greenCurvePoints.length > 0 ||
        parameters.blueCurvePoints.length > 0
      );
    case 'depth':
      return focalPoint !== null;
    default:
      return step.params.some((key) => parameters[key] !== DEFAULT_PARAMETERS[key]);
  }
}

/** The numbered workflow rail: pick which group of tools the inspector shows. */
export function EditorRail({ activeStep, onStepChange, parameters, focalPoint }: EditorRailProps) {
  const { t } = useTranslation();

  return (
    <nav
      aria-label={t('editor.rail.aria_label')}
      className="flex gap-1.5 overflow-x-auto pb-1 lg:flex-col lg:gap-0.5 lg:overflow-visible lg:pb-0"
    >
      {EDITOR_STEPS.map((step) => {
        const active = step.id === activeStep;
        const modified = stepIsModified(step, parameters, focalPoint);
        // Set the start / export brackets off from the numbered steps.
        const dividerBefore = step.id === 'frame' || step.id === 'export';
        return (
          <div key={step.id} className="contents">
            {dividerBefore && (
              <span className="hidden lg:my-1 lg:block lg:border-t lg:border-hairline" aria-hidden />
            )}
            <button
              type="button"
              aria-current={active ? 'step' : undefined}
              onClick={() => onStepChange(step.id)}
              className={`group flex shrink-0 items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-accent lg:w-full ${
                active
                  ? 'bg-accent-wash text-ink'
                  : 'text-muted hover:bg-white/[0.04] hover:text-ink'
              }`}
            >
              <span
                className={`grid h-5 w-5 shrink-0 place-items-center rounded-full border text-[11px] font-semibold tabular-nums ${
                  active ? 'border-accent/60 text-accent' : 'border-line-strong text-faint'
                }`}
              >
                {step.number ?? <StepBracketIcon id={step.id} />}
              </span>
              <span className="flex-1 truncate">{t(`editor.rail.${step.id}`)}</span>
              {modified && (
                <span
                  className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent"
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

function StepBracketIcon({ id }: { id: EditorStepId }) {
  if (id === 'start') {
    return (
      <svg viewBox="0 0 12 12" className="h-3 w-3 fill-current" aria-hidden>
        <path d="M6 0l1.3 3.4L11 4.7 8 7l.8 4L6 8.8 3.2 11 4 7 1 4.7l3.7-1.3z" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 12 12" className="h-3 w-3 stroke-current" fill="none" aria-hidden>
      <path d="M6 1.5v6M3.5 5.5 6 8l2.5-2.5M2.5 10.5h7" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}
