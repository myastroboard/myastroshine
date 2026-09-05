import { useEffect, useState } from 'react';

import { useTranslation } from '@/hooks/useTranslation';
import type { Preset } from '@/types';

export interface PresetButtonsProps {
  presets: Preset[];
  activePreset?: string;
  onPresetApply: (presetId: string) => void;
  /** Delete a user preset. Built-ins (`author === 'system'`) are never deletable. */
  onPresetDelete?: (presetId: string) => void;
}

/** Quick-apply preset chips; user presets carry a two-click delete. */
export function PresetButtons({
  presets,
  activePreset,
  onPresetApply,
  onPresetDelete,
}: PresetButtonsProps) {
  const { t } = useTranslation();
  const [confirmId, setConfirmId] = useState<string | null>(null);

  useEffect(() => {
    if (!confirmId) {
      return;
    }
    const timer = setTimeout(() => setConfirmId(null), 3000);
    return () => clearTimeout(timer);
  }, [confirmId]);

  return (
    <div className="flex flex-wrap gap-2">
      {presets.map((preset) => {
        const active = activePreset === preset.presetId;
        const deletable = Boolean(onPresetDelete) && preset.author !== 'system';
        const confirming = confirmId === preset.presetId;
        return (
          <div key={preset.presetId} className="group relative inline-flex">
            <button
              type="button"
              className={`chip ${active ? 'chip-active' : ''} ${deletable ? 'pr-8' : ''}`}
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

            {deletable && (
              <button
                type="button"
                className={`absolute right-1 top-1/2 grid h-5 w-5 -translate-y-1/2 place-items-center rounded transition ${
                  confirming
                    ? 'bg-danger-wash text-danger opacity-100'
                    : 'text-faint opacity-0 hover:bg-white/10 hover:text-danger focus-visible:opacity-100 group-hover:opacity-100'
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
