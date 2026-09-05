export interface ExportPanelProps {
  isProcessing?: boolean;
  canSendToAstroDex?: boolean;
  onDownload: () => void;
  onSendToAstroDex: () => void;
}

/** Getting the enhanced image out of the editor: download, or hand it to AstroDex. */
export function ExportPanel({
  isProcessing = false,
  canSendToAstroDex = false,
  onDownload,
  onSendToAstroDex,
}: ExportPanelProps) {
  return (
    <div className="panel flex flex-col gap-2.5">
      <h2 className="eyebrow">Export</h2>
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
            className="btn btn-amber"
            disabled={isProcessing}
            onClick={onSendToAstroDex}
          >
            Send to AstroDex
          </button>
        )}
      </div>
    </div>
  );
}
