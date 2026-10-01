import { useEffect, useState, type ComponentType } from 'react';

import {
  ClusterIcon,
  DeepFieldIcon,
  GalaxyIcon,
  MoonIcon,
  NebulaIcon,
  SlidersIcon,
  type IconProps,
} from '@/components/icons';
import { useTranslation } from '@/hooks/useTranslation';
import type { Preset } from '@/types';

export interface PresetButtonsProps {
  presets: Preset[];
  activePreset?: string;
  onPresetApply: (presetId: string) => void;
  /** Delete a user preset. Built-ins (`author === 'system'`) are never deletable. */
  onPresetDelete?: (presetId: string) => void;
}

/** The subject each built-in preset is tuned for; a user preset gets the sliders icon. */
const PRESET_ICONS: Record<string, ComponentType<IconProps>> = {
  system_nebula: NebulaIcon,
  system_galaxy: GalaxyIcon,
  system_deep_field: DeepFieldIcon,
  system_lunar: MoonIcon,
  system_cluster: ClusterIcon,
};

/** Quick-apply preset cards (icon, name, what it is for); user presets carry a
 * two-click delete. */
export function PresetButtons({
  presets,
  activePreset,
  onPresetApply,
  onPresetDelete,
}: PresetButtonsProps) {
  const { t } = useTranslation();
  const [confirmId, setConfirmId] = useState<string | null>(null);

  // Built-in presets are the same 5 for everyone, so their name / description
  // are translated; a user preset keeps the name the user typed.
  const label = (preset: Preset) =>
    preset.author === 'system' ? t(`presets.builtin.${preset.presetId}.name`) : preset.name;
  const description = (preset: Preset) =>
    preset.author === 'system'
      ? t(`presets.builtin.${preset.presetId}.description`)
      : preset.description;

  useEffect(() => {
    if (!confirmId) {
      return;
    }
    const timer = setTimeout(() => setConfirmId(null), 3000);
    return () => clearTimeout(timer);
  }, [confirmId]);

  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
      {presets.map((preset) => {
        const active = activePreset === preset.presetId;
        const deletable = Boolean(onPresetDelete) && preset.author !== 'system';
        const confirming = confirmId === preset.presetId;
        const Icon = PRESET_ICONS[preset.presetId] ?? SlidersIcon;
        const blurb = description(preset);
        return (
          <div key={preset.presetId} className="group relative flex">
            <button
              type="button"
              className={`option-card w-full ${active ? 'option-card-active' : ''} ${deletable ? 'pr-8' : ''}`}
              aria-pressed={active}
              aria-describedby={blurb ? `preset-blurb-${preset.presetId}` : undefined}
              onClick={() => onPresetApply(preset.presetId)}
            >
              <Icon className={`mt-0.5 h-5 w-5 ${active ? 'text-accent' : 'text-faint'}`} />
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="text-sm font-medium text-ink">{label(preset)}</span>
                {blurb && (
                  // Out of the button's name (that stays the preset name) but
                  // still announced, as its description.
                  <span
                    id={`preset-blurb-${preset.presetId}`}
                    aria-hidden
                    className="line-clamp-2 text-xs text-faint"
                  >
                    {blurb}
                  </span>
                )}
              </span>
            </button>

            {deletable && (
              <button
                type="button"
                className={`absolute right-1.5 top-1.5 grid h-5 w-5 place-items-center rounded transition ${
                  confirming
                    ? 'bg-danger-wash text-danger opacity-100'
                    : 'text-faint opacity-0 hover:bg-hover hover:text-danger focus-visible:opacity-100 group-hover:opacity-100'
                }`}
                aria-label={
                  confirming
                    ? t('preset_buttons.confirm_delete_aria', { name: preset.name })
                    : t('preset_buttons.delete_aria', { name: preset.name })
                }
                title={confirming ? t('preset_buttons.click_again_to_delete') : t('preset_buttons.delete_preset_title')}
                onClick={() => {
                  if (confirming) {
                    onPresetDelete?.(preset.presetId);
                    setConfirmId(null);
                  } else {
                    setConfirmId(preset.presetId);
                  }
                }}
              >
                <svg viewBox="0 0 12 12" className="h-3 w-3 stroke-current" aria-hidden>
                  {confirming ? (
                    <path d="M2.5 6.5 5 9l4.5-5.5" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  ) : (
                    <path d="M3 3l6 6M9 3l-6 6" strokeWidth="1.5" strokeLinecap="round" />
                  )}
                </svg>
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
