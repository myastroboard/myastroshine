import { useTranslation } from '@/hooks/useTranslation';
import type { StackResult } from '@/types';

export interface StackResultsProps {
  result: StackResult;
  onEnhance: () => void;
  onDownload: () => void;
}

/** Stacked composite preview + statistics (v1.1). */
export function StackResults({ result, onEnhance, onDownload }: StackResultsProps) {
  const { t } = useTranslation();
  const stats = result.statistics;

  if (result.status !== 'completed' || !stats || !result.stackedImageUrl) {
    return (
      <p className="text-sm text-faint">
        {result.error
          ? t('stacking.results.failed', { error: result.error })
          : t('stacking.results.status_ellipsis', { status: result.status })}
      </p>
    );
  }

  const rows: [string, string][] = [
    [t('stacking.results.frames_stacked'), String(stats.framesStacked)],
    [t('stacking.results.frames_rejected'), String(stats.framesRejected)],
    [t('stacking.combination_label'), stats.combinationMethod],
    [t('stacking.results.cosmic_rays_removed'), String(stats.cosmicRaysRemoved)],
    [t('stacking.results.registration_success'), `${stats.registrationSuccessRate}%`],
    [t('stacking.results.snr_improvement'), `${stats.snrImprovement.toFixed(2)}x`],
  ];

  return (
    <div className="flex flex-col gap-4">
      <img
        src={result.stackedImageUrl}
        alt={t('stacking.results.composite_alt')}
        className="w-full rounded-xl border border-hairline"
      />
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 rounded-lg border border-hairline bg-surface p-4 text-xs">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-baseline justify-between gap-2">
            <dt className="text-faint">{label}</dt>
            <dd className="tabular-nums text-ink">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="flex gap-2">
        <button type="button" className="btn btn-primary" onClick={onEnhance}>
          {t('stacking.results.enhance_composite')}
        </button>
        <button type="button" className="btn btn-outline" onClick={onDownload}>
          {t('stacking.results.download_composite')}
        </button>
      </div>
    </div>
  );
}
