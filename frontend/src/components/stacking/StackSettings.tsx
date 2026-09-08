import { useTranslation } from '@/hooks/useTranslation';
import type {
  CombinationMethod,
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
    </div>
  );
}
