import { useTranslation } from '@/hooks/useTranslation';
import type { StackSettings as StackSettingsValue } from '@/types';

export interface StackSettingsProps {
  settings: StackSettingsValue;
  onChange: (settings: StackSettingsValue) => void;
}

/** Stacking configuration panel: alignment, combination, rejection (v1.1+). */
export function StackSettings({ settings, onChange }: StackSettingsProps) {
  const { t } = useTranslation();
  return (
    <div className="panel flex flex-col gap-4">
      <label className="flex flex-col gap-1.5">
        <span className="label">{t('stacking.settings.alignment_label')}</span>
        <select
          className="field"
          value={settings.registrationMethod}
          onChange={(event) =>
            onChange({
              ...settings,
              registrationMethod: event.target.value as StackSettingsValue['registrationMethod'],
            })
          }
        >
          <option value="orb">{t('stacking.settings.orb_option')}</option>
          <option value="sift">{t('stacking.settings.sift_option')}</option>
        </select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="label">{t('stacking.combination_label')}</span>
        <select
          className="field"
          value={settings.combinationMethod}
          onChange={(event) =>
            onChange({
              ...settings,
              combinationMethod: event.target.value as StackSettingsValue['combinationMethod'],
            })
          }
        >
          <option value="median">{t('stacking.settings.median_option')}</option>
          <option value="mean">{t('stacking.settings.mean_option')}</option>
          <option value="sigma_clip">{t('stacking.settings.sigma_clip_option')}</option>
        </select>
      </label>

      <label className="flex items-center justify-between gap-2 text-sm text-muted">
        {t('stacking.cosmic_ray_rejection_label')}
        <input
          type="checkbox"
          className="size-4 accent-accent"
          checked={settings.cosmicRayRejection}
          onChange={(event) => onChange({ ...settings, cosmicRayRejection: event.target.checked })}
        />
      </label>

      <label className="flex items-center justify-between gap-2 text-sm text-muted">
        {t('stacking.background_normalization_label')}
        <input
          type="checkbox"
          className="size-4 accent-accent"
          checked={settings.backgroundNormalization}
          onChange={(event) =>
            onChange({ ...settings, backgroundNormalization: event.target.checked })
          }
        />
      </label>
    </div>
  );
}
