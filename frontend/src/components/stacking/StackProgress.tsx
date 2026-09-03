export interface StackStep {
  label: string;
  progressPercent: number;
}

export interface StackProgressProps {
  steps: StackStep[];
  currentMessage?: string;
}

/** Step-by-step stacking progress display (v1.1+). */
export function StackProgress({ steps, currentMessage }: StackProgressProps) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-white/10 p-4 text-sm">
      {steps.map((step) => (
        <div key={step.label} className="flex flex-col gap-1">
          <span className="flex justify-between">
            <span>{step.label}</span>
            <span className="text-gray-400">{step.progressPercent}%</span>
          </span>
          <span className="h-2 rounded bg-white/10">
            <span
              className="block h-full rounded bg-primary"
              style={{ width: `${step.progressPercent}%` }}
            />
          </span>
        </div>
      ))}
      {currentMessage && <p className="text-xs text-gray-400">{currentMessage}</p>}
    </div>
  );
}
