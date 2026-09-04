import { PARAMETER_BOUNDS, type ParameterBound, type ProcessingParameters } from '@/types';

export interface SliderPanelProps {
  parameters: ProcessingParameters;
  onParameterChange: (key: keyof ProcessingParameters, value: number) => void;
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
            <label key={bound.key} className="flex flex-col gap-1.5 text-sm">
              <span className="flex items-baseline justify-between">
                <span className="text-muted">{bound.label}</span>
                <span className="text-xs tabular-nums text-faint">{parameters[bound.key]}</span>
              </span>
              <input
                type="range"
                className="slider"
                min={bound.min}
                max={bound.max}
                step={bound.step}
                value={parameters[bound.key]}
                disabled={isProcessing}
                aria-label={bound.label}
                onChange={(event) => onParameterChange(bound.key, Number(event.target.value))}
              />
            </label>
          ))}
        </fieldset>
      ))}
    </div>
  );
}
