import type { StackResult } from '@/types';

export interface StackResultsProps {
  result: StackResult;
  onEnhance: () => void;
  onDownload: () => void;
}

/** Stacked composite preview + statistics (v1.1). */
export function StackResults({ result, onEnhance, onDownload }: StackResultsProps) {
  const stats = result.statistics;

  if (result.status !== 'completed' || !stats || !result.stackedImageUrl) {
    return (
      <p className="text-sm text-faint">
        {result.error ? `Stacking failed: ${result.error}` : `Stack ${result.status}...`}
      </p>
    );
  }

  const rows: [string, string][] = [
    ['Frames stacked', String(stats.framesStacked)],
    ['Frames rejected', String(stats.framesRejected)],
    ['Combination', stats.combinationMethod],
    ['Cosmic rays removed', String(stats.cosmicRaysRemoved)],
    ['Registration success', `${stats.registrationSuccessRate}%`],
    ['SNR improvement', `${stats.snrImprovement.toFixed(2)}x`],
  ];

  return (
    <div className="flex flex-col gap-4">
      <img
        src={result.stackedImageUrl}
        alt="Stacked composite"
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
          Enhance composite
        </button>
        <button type="button" className="btn btn-outline" onClick={onDownload}>
          Download composite
        </button>
      </div>
    </div>
  );
}
