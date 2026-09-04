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
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        className="btn btn-primary"
        disabled={isProcessing}
        onClick={onDownload}
      >
        Download
      </button>
      {canSendToAstroDex && (
        <button
          type="button"
          className="btn btn-outline"
          disabled={isProcessing}
          onClick={onSendToAstroDex}
        >
          Send to AstroDex
        </button>
      )}
      <button
        type="button"
        className="btn btn-outline"
        disabled={isProcessing}
        onClick={onSavePreset}
      >
        Save as preset
      </button>
    </div>
  );
}
