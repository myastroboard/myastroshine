import type { StackSettings as StackSettingsValue } from '@/types';

export interface StackSettingsProps {
  settings: StackSettingsValue;
  onChange: (settings: StackSettingsValue) => void;
}

/** Stacking configuration panel: alignment, combination, rejection (v1.1+). */
export function StackSettings({ settings, onChange }: StackSettingsProps) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-white/10 p-4 text-sm">
      <label className="flex justify-between gap-2">
        Alignment
        <select
          value={settings.registrationMethod}
          onChange={(event) =>
            onChange({ ...settings, registrationMethod: event.target.value as StackSettingsValue['registrationMethod'] })
          }
        >
          <option value="orb">ORB (fast)</option>
          <option value="sift">SIFT (accurate)</option>
        </select>
      </label>
      <label className="flex justify-between gap-2">
        Combination
        <select
          value={settings.combinationMethod}
          onChange={(event) =>
            onChange({ ...settings, combinationMethod: event.target.value as StackSettingsValue['combinationMethod'] })
          }
        >
          <option value="median">Median</option>
          <option value="mean">Mean</option>
          <option value="sigma_clip">Sigma-clip</option>
        </select>
      </label>
      <label className="flex items-center justify-between gap-2">
        Cosmic ray rejection
        <input
          type="checkbox"
          checked={settings.cosmicRayRejection}
          onChange={(event) => onChange({ ...settings, cosmicRayRejection: event.target.checked })}
        />
      </label>
      <label className="flex items-center justify-between gap-2">
        Background normalization
        <input
          type="checkbox"
          checked={settings.backgroundNormalization}
          onChange={(event) => onChange({ ...settings, backgroundNormalization: event.target.checked })}
        />
      </label>
    </div>
  );
}
