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
    <div className="flex flex-col gap-4 rounded-lg border border-white/10 p-4">
      {groups.map((group) => (
        <fieldset key={group} className="flex flex-col gap-2">
          <legend className="text-xs font-semibold uppercase tracking-wide text-gray-400">
            {GROUP_LABELS[group]}
          </legend>
          {PARAMETER_BOUNDS.filter((bound) => bound.group === group).map((bound) => (
            <label key={bound.key} className="flex flex-col gap-1 text-sm">
              <span className="flex justify-between">
                <span>{bound.label}</span>
                <span className="tabular-nums text-gray-400">{parameters[bound.key]}</span>
              </span>
              <input
                type="range"
                className="slider-input"
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

      <button type="button" className="self-start text-xs text-gray-300 underline" onClick={onReset}>
        Reset all
      </button>
    </div>
  );
}
