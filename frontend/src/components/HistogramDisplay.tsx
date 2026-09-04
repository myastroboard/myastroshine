import type { HistogramData } from '@/types';

export interface HistogramDisplayProps {
  data: HistogramData;
}

/** RGB histogram visualization (three overlaid channel curves). */
export function HistogramDisplay({ data }: HistogramDisplayProps) {
  const channels: Array<[keyof HistogramData, string]> = [
    ['r', 'stroke-red-400'],
    ['g', 'stroke-green-400'],
    ['b', 'stroke-blue-400'],
  ];
  const max = Math.max(1, ...data.r, ...data.g, ...data.b);

  return (
    <svg viewBox="0 0 256 64" className="h-16 w-full" role="img" aria-label="RGB histogram">
      {channels.map(([channel, className]) => (
        <polyline
          key={channel}
          className={`${className} fill-none`}
          strokeWidth={1}
          points={data[channel]
            .map((value, index) => `${index},${64 - (value / max) * 64}`)
            .join(' ')}
        />
      ))}
    </svg>
  );
}
