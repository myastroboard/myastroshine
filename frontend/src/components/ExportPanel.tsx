import { useTranslation } from '@/hooks/useTranslation';

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
  const { t } = useTranslation();
  return (
    <div className="panel flex flex-col gap-2.5">
      <h2 className="eyebrow">{t('export_panel.heading')}</h2>
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
    </div>
  );
}
