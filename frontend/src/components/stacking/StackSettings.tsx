import type { StackSettings as StackSettingsValue } from '@/types';

export interface StackSettingsProps {
  settings: StackSettingsValue;
  onChange: (settings: StackSettingsValue) => void;
}

/** Stacking configuration panel: alignment, combination, rejection (v1.1+). */
export function StackSettings({ settings, onChange }: StackSettingsProps) {
  return (
    <div className="panel flex flex-col gap-4">
      <label className="flex flex-col gap-1.5">
        <span className="label">Alignment</span>
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
          <option value="orb">ORB (fast)</option>
          <option value="sift">SIFT (accurate)</option>
        </select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="label">Combination</span>
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
          <option value="median">Median</option>
          <option value="mean">Mean</option>
          <option value="sigma_clip">Sigma-clip</option>
        </select>
      </label>

      <label className="flex items-center justify-between gap-2 text-sm text-muted">
        Cosmic ray rejection
        <input
          type="checkbox"
          className="size-4 accent-accent"
          checked={settings.cosmicRayRejection}
          onChange={(event) => onChange({ ...settings, cosmicRayRejection: event.target.checked })}
        />
      </label>

      <label className="flex items-center justify-between gap-2 text-sm text-muted">
        Background normalization
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
