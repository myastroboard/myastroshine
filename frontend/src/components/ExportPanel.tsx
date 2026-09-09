import { useTranslation } from '@/hooks/useTranslation';

export interface ExportPanelProps {
  isProcessing?: boolean;
  /** True when the session was opened from an AstroDex handoff. */
  canReturnToAstroDex?: boolean;
  astrodexObjectName?: string | null;
  astrodexReturning?: boolean;
  astrodexReturned?: boolean;
  astrodexError?: string | null;
  onDownload: () => void;
  onReturnToAstroDex: () => void;
  onSaveAsPreset: () => void;
}

/** Getting the enhanced image out of the editor: download, send it back to the
 * AstroDex object it came from, or save the current parameters as a preset. */
export function ExportPanel({
  isProcessing = false,
  canReturnToAstroDex = false,
  astrodexObjectName = null,
  astrodexReturning = false,
  astrodexReturned = false,
  astrodexError = null,
  onDownload,
  onReturnToAstroDex,
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
        {canReturnToAstroDex && (
          <button
            type="button"
            className="btn btn-amber"
            disabled={isProcessing || astrodexReturning}
            onClick={onReturnToAstroDex}
          >
            {astrodexReturning
              ? t('export_panel.returning')
              : t('export_panel.return_to_astrodex')}
          </button>
        )}
      </div>
      {canReturnToAstroDex && !astrodexReturned && !astrodexError && (
        <p className="text-xs text-faint">
          {astrodexObjectName
            ? t('export_panel.return_hint_named', { object: astrodexObjectName })
            : t('export_panel.return_hint')}
        </p>
      )}
      {canReturnToAstroDex && astrodexReturned && !astrodexError && (
        <p className="text-xs text-success">{t('export_panel.returned')}</p>
      )}
      {canReturnToAstroDex && astrodexError && (
        <p className="rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-xs text-danger">
          {t('export_panel.return_failed', { error: astrodexError })}
        </p>
      )}
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
