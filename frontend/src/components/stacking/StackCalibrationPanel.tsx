import { useRef } from 'react';

import { useTranslation } from '@/hooks/useTranslation';
import type { CalibrationKind, CalibrationSummary } from '@/types';

export interface StackCalibrationPanelProps {
  calibration: CalibrationSummary;
  cosmeticCorrection: boolean;
  /** Uploading in progress / the stack is running - lock the controls. */
  disabled: boolean;
  onAdd: (kind: CalibrationKind, files: File[]) => void;
  onClear: (kind: CalibrationKind) => void;
  onToggleCosmetic: (value: boolean) => void;
}

const KINDS: { kind: CalibrationKind; count: keyof CalibrationSummary['frames'] }[] = [
  { kind: 'dark', count: 'dark' },
  { kind: 'flat', count: 'flat' },
  { kind: 'bias', count: 'bias' },
  { kind: 'dark_flat', count: 'darkFlat' },
];

const CAL_ACCEPT = '.png,.tiff,.tif,.fits,.fit,.fts,.cr2,.cr3,.nef,.arw,.dng,.orf,.rw2,.pef,.raf';

/** Optional master dark / flat / bias frames for a stack (Phase 2). */
export function StackCalibrationPanel({
  calibration,
  cosmeticCorrection,
  disabled,
  onAdd,
  onClear,
  onToggleCosmetic,
}: StackCalibrationPanelProps) {
  const { t } = useTranslation();
  const hasDefectSource = calibration.frames.dark > 0 || calibration.frames.flat > 0;

  return (
    <div className="panel flex flex-col gap-3">
      <h3 className="text-sm font-medium text-ink">{t('stacking.calibration.title')}</h3>
      <p className="text-xs text-faint">{t('stacking.calibration.hint')}</p>

      <ul className="flex flex-col divide-y divide-hairline">
        {KINDS.map(({ kind, count }) => (
          <CalibrationRow
            key={kind}
            label={t(`stacking.calibration.kinds.${kind}`)}
            count={calibration.frames[count]}
            disabled={disabled}
            onAdd={(files) => onAdd(kind, files)}
            onClear={() => onClear(kind)}
            addLabel={t('stacking.calibration.add')}
            clearLabel={t('stacking.calibration.clear')}
            countLabel={t('stacking.calibration.count', { n: calibration.frames[count] })}
          />
        ))}
      </ul>

      <label className="flex items-center gap-2 text-xs text-muted">
        <input
          type="checkbox"
          className="size-3.5 accent-accent"
          checked={cosmeticCorrection}
          disabled={disabled || !hasDefectSource}
          onChange={(event) => onToggleCosmetic(event.target.checked)}
        />
        {t('stacking.calibration.cosmetic_label')}
      </label>
      <p className="text-[11px] text-ghost">{t('stacking.calibration.masters_note')}</p>
    </div>
  );
}

interface CalibrationRowProps {
  label: string;
  count: number;
  disabled: boolean;
  onAdd: (files: File[]) => void;
  onClear: () => void;
  addLabel: string;
  clearLabel: string;
  countLabel: string;
}

function CalibrationRow({
  label,
  count,
  disabled,
  onAdd,
  onClear,
  addLabel,
  clearLabel,
  countLabel,
}: CalibrationRowProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <li className="flex items-center justify-between gap-2 py-2 text-xs">
      <span className="text-muted">{label}</span>
      <span className="flex items-center gap-2">
        <span className="tabular-nums text-faint">{count > 0 ? countLabel : ''}</span>
        {count > 0 && (
          <button
            type="button"
            className="text-faint hover:text-danger disabled:opacity-40"
            disabled={disabled}
            onClick={onClear}
          >
            {clearLabel}
          </button>
        )}
        <button
          type="button"
          className="chip disabled:opacity-40"
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
        >
          {addLabel}
        </button>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={CAL_ACCEPT}
          className="hidden"
          onChange={(event) => {
            onAdd(Array.from(event.target.files ?? []));
            event.target.value = '';
          }}
        />
      </span>
    </li>
  );
}
