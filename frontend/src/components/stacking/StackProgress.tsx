import { useTranslation } from '@/hooks/useTranslation';

export interface StackProgressProps {
  /** Overall completion, 0-100. */
  percent: number;
  /** Backend step key, e.g. `registration`, `integration`, `done`. */
  currentStep: string;
  /** Short "340/1066"-style counter for the active step, if any. */
  detail?: string;
}

const PIPELINE: { key: string; translationKey: string }[] = [
  { key: 'upload', translationKey: 'stacking.steps.upload' },
  { key: 'calibration', translationKey: 'stacking.steps.calibration' },
  { key: 'registration', translationKey: 'stacking.steps.registration' },
  { key: 'normalization', translationKey: 'stacking.steps.normalization' },
  { key: 'integration', translationKey: 'stacking.steps.integration' },
];

/** Fold the extra backend step keys onto a pipeline entry. */
function pipelineKey(step: string): string {
  return step === 'post-processing' ? 'integration' : step;
}

/** Step-by-step stacking progress display (v1.1+). */
export function StackProgress({ percent, currentStep, detail }: StackProgressProps) {
  const { t } = useTranslation();
  const key = pipelineKey(currentStep);
  const activeIndex = PIPELINE.findIndex((step) => step.key === key);
  const done = currentStep === 'done';

  return (
    <div className="panel flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <span className="flex items-baseline justify-between">
          <span className="eyebrow">{t('stacking.progress.heading')}</span>
          <span className="text-xs tabular-nums text-faint">{percent}%</span>
        </span>
        <span className="h-1 overflow-hidden rounded-full bg-line">
          <span
            className="block h-full rounded-full bg-accent transition-[width] duration-300 ease-out"
            style={{ width: `${percent}%` }}
          />
        </span>
      </div>

      <ul className="flex flex-col gap-2 text-xs">
        {PIPELINE.map((step, index) => {
          const state =
            done || index < activeIndex ? 'done' : index === activeIndex ? 'active' : 'pending';
          return (
            <li key={step.key} className="flex items-center gap-2.5">
              <span
                aria-hidden
                className={
                  state === 'done'
                    ? 'h-1.5 w-1.5 rounded-full bg-accent'
                    : state === 'active'
                      ? 'h-1.5 w-1.5 rounded-full bg-accent-strong ring-2 ring-accent/25'
                      : 'h-1.5 w-1.5 rounded-full bg-line-strong'
                }
              />
              <span className={state === 'pending' ? 'text-ghost' : 'text-muted'}>
                {t(step.translationKey)}
              </span>
              {state === 'active' && detail && (
                <span className="tabular-nums text-faint">· {detail}</span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
