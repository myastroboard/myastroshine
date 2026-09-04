export interface StackProgressProps {
  /** Overall completion, 0-100. */
  percent: number;
  /** Backend step key, e.g. `registration`, `combination`, `done`. */
  currentStep: string;
}

const PIPELINE: { key: string; label: string }[] = [
  { key: 'registration', label: 'Registration' },
  { key: 'background_normalization', label: 'Background normalization' },
  { key: 'cosmic_ray_rejection', label: 'Cosmic ray rejection' },
  { key: 'combination', label: 'Combination' },
];

/** Step-by-step stacking progress display (v1.1+). */
export function StackProgress({ percent, currentStep }: StackProgressProps) {
  const activeIndex = PIPELINE.findIndex((step) => step.key === currentStep);
  const done = currentStep === 'done';

  return (
    <div className="panel flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <span className="flex items-baseline justify-between">
          <span className="eyebrow">Stacking</span>
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
              <span className={state === 'pending' ? 'text-ghost' : 'text-muted'}>{step.label}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
