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
  onResetSection: (keys: SliderParameterKey[]) => void;
  isProcessing?: boolean;
  starMaskEnabled?: boolean;
  onStarMaskToggle?: (enabled: boolean) => void;
  starMaskSourceCount?: number | null;
  starMaskLoading?: boolean;
}

/** How many decimals a value at this step should display - 0.01 -> 2, 1 -> 0. */
function decimalPlaces(step: number): number {
  const text = step.toString();
  const dot = text.indexOf('.');
  return dot === -1 ? 0 : text.length - dot - 1;
}

interface SectionMeta {
  label: string;
  help: string;
  defaultOpen: boolean;
}

const SECTIONS: Record<ParameterBound['group'], SectionMeta> = {
  light: {
    label: 'Light',
    help: 'Overall exposure and tonal balance - how bright, contrasty, and full of shadow and highlight detail the image reads.',
    defaultOpen: true,
  },
  colour: {
    label: 'Colour',
    help: 'Hue, saturation, and white balance - how vivid and how warm or cool the image looks.',
    defaultOpen: true,
  },
  detail: {
    label: 'Detail',
    help: 'Local texture: micro-contrast, noise reduction, and sharpening.',
    defaultOpen: false,
  },
  star: {
    label: 'Stars',
    help: 'How individual stars are detected and shrunk, so faint nebulosity stands out.',
    defaultOpen: false,
  },
  depth: {
    label: 'Depth',
    help: 'Strength of the parallax effect in the Depth Shift viewer.',
    defaultOpen: false,
  },
};

const SECTION_ORDER = Object.keys(SECTIONS) as ParameterBound['group'][];

/** Parameter adjustment sliders, grouped into named, collapsible sections. */
export function SliderPanel({
  parameters,
  onParameterChange,
  onReset,
  onResetSection,
  isProcessing = false,
  starMaskEnabled = false,
  onStarMaskToggle,
  starMaskSourceCount = null,
  starMaskLoading = false,
}: SliderPanelProps) {
  return (
    <div className="panel flex flex-col gap-1">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="eyebrow">Adjustments</h2>
        <button type="button" className="btn btn-ghost btn-sm -mr-2" onClick={onReset}>
          Reset all
        </button>
      </div>

      {SECTION_ORDER.map((group) => {
        const bounds = PARAMETER_BOUNDS.filter((bound) => bound.group === group);
        const section = SECTIONS[group];
        return (
          <details
            key={group}
            className="group/section border-t border-hairline py-3 first:border-t-0 first:pt-0"
            open={section.defaultOpen}
          >
            <summary className="flex cursor-pointer list-none items-center justify-between gap-2 [&::-webkit-details-marker]:hidden">
              <span className="inline-flex items-center gap-1.5">
                <svg
                  viewBox="0 0 10 10"
                  className="h-2.5 w-2.5 shrink-0 stroke-faint transition-transform duration-150 group-open/section:rotate-90"
                  aria-hidden
                >
                  <path
                    d="M3 1l4 4-4 4"
                    fill="none"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <span className="eyebrow">{section.label}</span>
              </span>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  onResetSection(bounds.map((bound) => bound.key));
                }}
              >
                Reset
              </button>
            </summary>

            <p className="mb-3 mt-1.5 text-xs text-faint">{section.help}</p>

            <div className="flex flex-col gap-3">
              {bounds.map((bound) => (
                <div key={bound.key} className="flex flex-col gap-1.5 text-sm">
                  <span className="flex items-baseline justify-between">
                    <span className="inline-flex items-center gap-1 text-muted">
                      <label htmlFor={`param-${bound.key}`}>{bound.label}</label>
                      <ParameterHint paramKey={bound.key} label={bound.label} hint={bound.hint} />
                    </span>
                    <span className="text-xs tabular-nums text-faint">
                      {parameters[bound.key].toFixed(decimalPlaces(bound.step))}
                    </span>
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
              {group === 'star' && onStarMaskToggle && (
                <label className="flex items-center justify-between gap-2 text-sm text-muted">
                  <span className="inline-flex items-center gap-1.5">
                    Show star mask
                    {starMaskEnabled && (
                      <span className="text-xs tabular-nums text-faint">
                        {starMaskLoading
                          ? '...'
                          : starMaskSourceCount !== null
                            ? `${starMaskSourceCount} sources`
                            : ''}
                      </span>
                    )}
                  </span>
                  <input
                    type="checkbox"
                    className="size-4 accent-accent"
                    checked={starMaskEnabled}
                    onChange={(event) => onStarMaskToggle(event.target.checked)}
                  />
                </label>
              )}
            </div>
          </details>
        );
      })}
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
