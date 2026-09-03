import type { StackResult } from '@/types';

export interface StackResultsProps {
  result: StackResult;
  onEnhance: () => void;
  onDownload: () => void;
}

/** Stacked composite preview + statistics (v1.1+). */
export function StackResults({ result, onEnhance, onDownload }: StackResultsProps) {
  return (
    <div className="flex flex-col gap-4">
      <img src={result.stackedImageUrl} alt="Stacked composite" className="w-full rounded-lg" />
      <dl className="grid grid-cols-2 gap-2 text-xs">
        <dt className="text-gray-400">Frames stacked</dt>
        <dd>{result.frameCount}</dd>
        <dt className="text-gray-400">Combination</dt>
        <dd>{result.combinationMethod}</dd>
        <dt className="text-gray-400">Cosmic rays removed</dt>
        <dd>{result.cosmicRaysRemoved}</dd>
        <dt className="text-gray-400">Registration success</dt>
        <dd>{result.registrationSuccessRate}%</dd>
        <dt className="text-gray-400">SNR improvement</dt>
        <dd>{result.estimatedSnrImprovement.toFixed(2)}x</dd>
      </dl>
      <div className="flex gap-3">
        <button type="button" className="rounded-md bg-primary px-4 py-2 text-sm" onClick={onEnhance}>
          Enhance composite
        </button>
        <button type="button" className="rounded-md border border-white/20 px-4 py-2 text-sm" onClick={onDownload}>
          Download composite
        </button>
      </div>
    </div>
  );
}
