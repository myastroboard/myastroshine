import type { Preset } from '@/types';

export interface PresetButtonsProps {
  presets: Preset[];
  activePreset?: string;
  onPresetApply: (presetId: string) => void;
}

const PRESET_ICONS: Record<string, string> = {
  Nebula: 'star',
  Galaxy: 'galaxy',
  'Deep Field': 'telescope',
  Lunar: 'moon',
  Cluster: 'sparkles',
};

/** Quick-apply preset buttons. */
export function PresetButtons({ presets, activePreset, onPresetApply }: PresetButtonsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {presets.map((preset) => (
        <button
          key={preset.presetId}
          type="button"
          className={`preset-button border ${
            activePreset === preset.presetId ? 'border-primary bg-primary/20' : 'border-white/15'
          }`}
          onClick={() => onPresetApply(preset.presetId)}
          title={preset.description}
        >
          <span aria-hidden className="text-xs text-gray-400">
            {PRESET_ICONS[preset.name] ?? 'preset'}
          </span>
          {preset.name}
        </button>
      ))}
    </div>
  );
}
