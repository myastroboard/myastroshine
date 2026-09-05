import { useTranslation } from '@/hooks/useTranslation';

export interface ExportPanelProps {
  isProcessing?: boolean;
  canSendToAstroDex?: boolean;
  onDownload: () => void;
  onSendToAstroDex: () => void;
  onSaveAsPreset: () => void;
}

/** Getting the enhanced image out of the editor: download, hand it to AstroDex,
 * or save the current parameters as a reusable preset. */
export function ExportPanel({
  isProcessing = false,
  canSendToAstroDex = false,
  onDownload,
  onSendToAstroDex,
  onSaveAsPreset,
}: ExportPanelProps) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn btn-primary"
          disabled={isProcessing}
          onClick={onDownload}
        >
          {t('export_panel.download')}
        </button>
        {canSendToAstroDex && (
          <button
            type="button"
            className="btn btn-amber"
            disabled={isProcessing}
            onClick={onSendToAstroDex}
          >
            {t('export_panel.send_to_astrodex')}
          </button>
        )}
      </div>
      <button
        type="button"
        className="btn btn-outline btn-sm self-start"
        disabled={isProcessing}
        onClick={onSaveAsPreset}
      >
        {t('editor.save_as_preset')}
      </button>
    </div>
  );
}
