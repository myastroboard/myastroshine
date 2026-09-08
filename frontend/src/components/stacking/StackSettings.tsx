import { useTranslation } from '@/hooks/useTranslation';
import type {
  CombinationMethod,
  DrizzleFactor,
  QualityFilter,
  RegistrationTransform,
  RejectionAlgo,
  StackSettings as StackSettingsValue,
  StackWeighting,
} from '@/types';

export interface StackSettingsProps {
  settings: StackSettingsValue;
  onChange: (settings: StackSettingsValue) => void;
}

const TRANSFORMS: RegistrationTransform[] = ['translation', 'similarity', 'affine'];
const COMBINATIONS: CombinationMethod[] = ['average', 'median'];
const REJECTIONS: RejectionAlgo[] = ['none', 'sigma', 'winsorized_sigma'];
const WEIGHTINGS: StackWeighting[] = ['none', 'noise', 'quality'];
const QUALITY_FILTERS: QualityFilter[] = ['off', 'lenient', 'moderate', 'strict'];
const DRIZZLE_FACTORS: DrizzleFactor[] = [1, 2, 3];

/** Stacking configuration panel: registration, combination, rejection, weighting. */
export function StackSettings({ settings, onChange }: StackSettingsProps) {
  const { t } = useTranslation();

  return (
    <div className="panel flex flex-col gap-4">
      <label className="flex flex-col gap-1.5">
        <span className="label">{t('stacking.settings.transform_label')}</span>
        <select
          className="field"
          value={settings.registrationTransform}
          onChange={(event) =>
            onChange({
              ...settings,
              registrationTransform: event.target.value as RegistrationTransform,
            })
          }
        >
          {TRANSFORMS.map((value) => (
            <option key={value} value={value}>
              {t(`stacking.settings.transform.${value}`)}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="label">{t('stacking.combination_label')}</span>
        <select
          className="field"
          value={settings.combinationMethod}
          onChange={(event) =>
            onChange({ ...settings, combinationMethod: event.target.value as CombinationMethod })
          }
        >
          {COMBINATIONS.map((value) => (
            <option key={value} value={value}>
              {t(`stacking.settings.combination.${value}`)}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="label">{t('stacking.settings.rejection_label')}</span>
        <select
          className="field"
          value={settings.rejectionAlgo}
          onChange={(event) =>
            onChange({ ...settings, rejectionAlgo: event.target.value as RejectionAlgo })
          }
        >
          {REJECTIONS.map((value) => (
            <option key={value} value={value}>
              {t(`stacking.settings.rejection.${value}`)}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="label">{t('stacking.settings.weighting_label')}</span>
        <select
          className="field"
          value={settings.weighting}
          onChange={(event) =>
            onChange({ ...settings, weighting: event.target.value as StackWeighting })
          }
        >
          {WEIGHTINGS.map((value) => (
            <option key={value} value={value}>
              {t(`stacking.settings.weighting.${value}`)}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="label">{t('stacking.settings.quality_label')}</span>
        <select
          className="field"
          value={settings.qualityFilter}
          onChange={(event) =>
            onChange({ ...settings, qualityFilter: event.target.value as QualityFilter })
          }
        >
          {QUALITY_FILTERS.map((value) => (
            <option key={value} value={value}>
              {t(`stacking.settings.quality.${value}`)}
            </option>
          ))}
        </select>
        <span className="text-[11px] text-ghost">{t('stacking.settings.quality_hint')}</span>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="label">{t('stacking.settings.drizzle_label')}</span>
        <select
          className="field"
          value={settings.drizzleFactor}
          onChange={(event) =>
            onChange({
              ...settings,
              drizzleFactor: Number(event.target.value) as DrizzleFactor,
            })
          }
        >
          {DRIZZLE_FACTORS.map((value) => (
            <option key={value} value={value}>
              {t(`stacking.settings.drizzle.${value}`)}
            </option>
          ))}
        </select>
        <span className="text-[11px] text-ghost">{t('stacking.settings.drizzle_hint')}</span>
      </label>

      <label className="flex items-start gap-2">
        <input
          type="checkbox"
          className="mt-0.5 size-3.5 accent-accent"
          checked={settings.postProcess}
          onChange={(event) => onChange({ ...settings, postProcess: event.target.checked })}
        />
        <span className="flex flex-col gap-0.5">
          <span className="label">{t('stacking.settings.post_process_label')}</span>
          <span className="text-[11px] text-ghost">
            {t('stacking.settings.post_process_hint')}
          </span>
        </span>
      </label>
    </div>
  );
}
