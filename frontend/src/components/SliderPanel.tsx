import {
  PARAMETER_BOUNDS,
  type ParameterBound,
  type ProcessingParameters,
  type SliderParameterKey,
} from '@/types';

export interface SliderPanelProps {
  parameters: ProcessingParameters;
  onParameterChange: (key: SliderParameterKey, value: number) => void;
  onReset: () => void;
  isProcessing?: boolean;
}

const GROUP_LABELS: Record<ParameterBound['group'], string> = {
  basic: 'Basic',
  tone: 'Tone',
  noise: 'Noise',
  star: 'Stars',
  sharp: 'Sharpness',
  color: 'Color',
  depth: 'Depth',
};

/** Parameter adjustment sliders, grouped by category. */
export function SliderPanel({
  parameters,
  onParameterChange,
  onReset,
  isProcessing = false,
}: SliderPanelProps) {
  const groups = Object.keys(GROUP_LABELS) as ParameterBound['group'][];

  return (
    <div className="panel flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h2 className="eyebrow">Adjustments</h2>
        <button type="button" className="btn btn-ghost btn-sm -mr-2" onClick={onReset}>
          Reset all
        </button>
      </div>

      {groups.map((group) => (
        <fieldset key={group} className="flex flex-col gap-3">
          <legend className="mb-1 text-xs font-medium text-faint">{GROUP_LABELS[group]}</legend>
          {PARAMETER_BOUNDS.filter((bound) => bound.group === group).map((bound) => (
            <div key={bound.key} className="flex flex-col gap-1.5 text-sm">
              <span className="flex items-baseline justify-between">
                <span className="inline-flex items-center gap-1 text-muted">
                  <label htmlFor={`param-${bound.key}`}>{bound.label}</label>
                  <ParameterHint paramKey={bound.key} label={bound.label} hint={bound.hint} />
                </span>
                <span className="text-xs tabular-nums text-faint">{parameters[bound.key]}</span>
              </span>
              <input
                id={`param-${bound.key}`}
                type="range"
                className="slider"
                min={bound.min}
                max={bound.max}
                step={bound.step}
                value={parameters[bound.key]}
                disabled={isProcessing}
                onChange={(event) => onParameterChange(bound.key, Number(event.target.value))}
              />
            </div>
          ))}
        </fieldset>
      ))}
    </div>
  );
}

/** Small "i" affordance; reveals `hint` in a popover on hover or keyboard focus. */
function ParameterHint({
  paramKey,
  label,
  hint,
}: {
  paramKey: SliderParameterKey;
  label: string;
  hint: string;
}) {
  const tooltipId = `param-hint-${paramKey}`;
  return (
    <span className="group/hint relative inline-flex">
      <button
        type="button"
        aria-describedby={tooltipId}
        aria-label={`About ${label}`}
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
