export interface ActionButtonsProps {
  sessionId: string;
  isProcessing?: boolean;
  canSendToAstroDex?: boolean;
  onDownload: () => void;
  onSendToAstroDex: () => void;
  onSavePreset: () => void;
}

/** Download / Send to AstroDex / Save preset actions. */
export function ActionButtons({
  isProcessing = false,
  canSendToAstroDex = false,
  onDownload,
  onSendToAstroDex,
  onSavePreset,
}: ActionButtonsProps) {
  return (
    <div className="flex flex-wrap gap-3">
      <button
        type="button"
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium disabled:opacity-50"
        disabled={isProcessing}
        onClick={onDownload}
      >
        Download
      </button>
      {canSendToAstroDex && (
        <button
          type="button"
          className="rounded-md bg-secondary px-4 py-2 text-sm font-medium disabled:opacity-50"
          disabled={isProcessing}
          onClick={onSendToAstroDex}
        >
          Send to AstroDex
        </button>
      )}
      <button
        type="button"
        className="rounded-md border border-white/20 px-4 py-2 text-sm disabled:opacity-50"
        disabled={isProcessing}
        onClick={onSavePreset}
      >
        Save as preset
      </button>
    </div>
  );
}
