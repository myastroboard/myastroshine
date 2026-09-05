import { useTranslation } from '@/hooks/useTranslation';
import {
  PARAMETER_BOUND_BY_KEY,
  type ProcessingParameters,
  type SliderParameterKey,
} from '@/types';

export interface SliderGroupProps {
  /** Parameters to render, in display order. */
  keys: SliderParameterKey[];
  parameters: ProcessingParameters;
  onParameterChange: (key: SliderParameterKey, value: number) => void;
  isProcessing?: boolean;
}

/** How many decimals a value at this step should display - 0.01 -> 2, 1 -> 0. */
function decimalPlaces(step: number): number {
  const text = step.toString();
  const dot = text.indexOf('.');
  return dot === -1 ? 0 : text.length - dot - 1;
}

/** A vertical list of labelled adjustment sliders with per-parameter hints. */
export function SliderGroup({
  keys,
  parameters,
  onParameterChange,
  isProcessing = false,
}: SliderGroupProps) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col gap-3">
      {keys.map((key) => {
        const bound = PARAMETER_BOUND_BY_KEY[key];
        if (!bound) {
          return null;
        }
        const label = t(`slider_panel.params.${key}.label`);
        const hint = t(`slider_panel.params.${key}.hint`);
        return (
          <div key={key} className="flex flex-col gap-1.5 text-sm">
            <span className="flex items-baseline justify-between">
              <span className="inline-flex items-center gap-1 text-muted">
                <label htmlFor={`param-${key}`}>{label}</label>
                <ParameterHint paramKey={key} label={label} hint={hint} />
              </span>
              <span className="text-xs tabular-nums text-faint">
                {parameters[key].toFixed(decimalPlaces(bound.step))}
              </span>
            </span>
            <input
              id={`param-${key}`}
              type="range"
              className="slider"
              min={bound.min}
              max={bound.max}
              step={bound.step}
              value={parameters[key]}
              disabled={isProcessing}
              onChange={(event) => onParameterChange(key, Number(event.target.value))}
            />
          </div>
        );
      })}
    </div>
  );
}

/** Small "i" affordance; reveals `hint` in a popover on hover or keyboard focus. */
export function ParameterHint({
  paramKey,
  label,
  hint,
}: {
  paramKey: SliderParameterKey;
  label: string;
  hint: string;
}) {
  const { t } = useTranslation();
  const tooltipId = `param-hint-${paramKey}`;
  return (
    <span className="group/hint relative inline-flex">
      <button
        type="button"
        aria-describedby={tooltipId}
        aria-label={t('slider_panel.about_param_aria', { label })}
        className="grid h-4 w-4 shrink-0 place-items-center rounded-full border border-line-strong text-[10px] font-semibold leading-none text-muted outline-none transition-colors hover:border-accent/60 hover:text-ink focus-visible:border-accent/60 focus-visible:text-ink"
      >
        i
      </button>
      <span
        id={tooltipId}
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-0 z-20 mb-1.5 w-52 rounded-md border border-line bg-overlay px-2.5 py-1.5 text-xs font-normal text-muted opacity-0 shadow-pop transition-opacity duration-100 group-hover/hint:opacity-100 group-focus-within/hint:opacity-100"
      >
        {hint}
      </span>
    </span>
  );
}
