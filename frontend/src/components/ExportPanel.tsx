import { useState } from 'react';

import { useTranslation } from '@/hooks/useTranslation';

export interface ExportPanelProps {
  isProcessing?: boolean;
  /** True when the session was opened from an AstroDex handoff. */
  canReturnToAstroDex?: boolean;
  astrodexObjectName?: string | null;
  astrodexReturning?: boolean;
  astrodexReturned?: boolean;
  astrodexError?: string | null;
  /** Pre-filled value for the filename field (no extension). */
  defaultFilename?: string;
  onDownload: (filename: string) => void;
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
  defaultFilename = '',
  onDownload,
  onReturnToAstroDex,
  onSaveAsPreset,
}: ExportPanelProps) {
  const { t } = useTranslation();
  const [filename, setFilename] = useState(defaultFilename);

  const trimmed = filename.trim();

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-col gap-1.5">
        <span className="label" id="export-filename-label">
          {t('export_panel.filename_label')}
        </span>
        <span className="flex items-stretch">
          <input
            className="field min-w-0 flex-1 rounded-r-none"
            value={filename}
            spellCheck={false}
            autoComplete="off"
            aria-labelledby="export-filename-label"
            onChange={(event) => setFilename(event.target.value)}
          />
          <span className="inline-flex items-center rounded-r-md border border-l-0 border-line bg-overlay px-2 text-xs text-faint">
            .jpg
          </span>
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn btn-primary"
          disabled={isProcessing || trimmed === ''}
          onClick={() => onDownload(trimmed || defaultFilename)}
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
