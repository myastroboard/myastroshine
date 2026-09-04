import type { Preset } from '@/types';

export interface PresetButtonsProps {
  presets: Preset[];
  activePreset?: string;
  onPresetApply: (presetId: string) => void;
}

/** Quick-apply preset buttons. */
export function PresetButtons({ presets, activePreset, onPresetApply }: PresetButtonsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {presets.map((preset) => {
        const active = activePreset === preset.presetId;
        return (
          <button
            key={preset.presetId}
            type="button"
            className={`chip ${active ? 'chip-active' : ''}`}
            aria-pressed={active}
            onClick={() => onPresetApply(preset.presetId)}
            title={preset.description}
          >
            <span
              aria-hidden
              className={`h-1.5 w-1.5 rounded-full ${active ? 'bg-accent' : 'bg-line-strong'}`}
            />
            {preset.name}
          </button>
        );
      })}
    </div>
  );
}
