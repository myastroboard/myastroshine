import { useState } from 'react';

import { CheckCircleIcon, DownloadIcon } from '@/components/icons';
import { useTranslation } from '@/hooks/useTranslation';

export interface ExportPanelProps {
  isProcessing?: boolean;
  /** True when the session was opened from an Astrodex handoff. */
  canReturnToAstroDex?: boolean;
  astrodexObjectName?: string | null;
  astrodexReturning?: boolean;
  astrodexReturned?: boolean;
  astrodexError?: string | null;
  /** Pre-filled value for the filename field (no extension). */
  defaultFilename?: string;
  /** The edited image, shown as the "ready" thumbnail. Omitted -> no thumbnail. */
  resultUrl?: string;
  /** Labels of the workflow steps that changed the image, for the recap line. */
  touchedSteps?: string[];
  onDownload: (filename: string) => void;
  onReturnToAstroDex: () => void;
  onSaveAsPreset: () => void;
}

/** The end of the workflow: a "ready" moment with the result and a recap of
 * what was done, then getting the image out - download it, send it back to the
 * Astrodex object it came from, or keep the settings for later photos. */
export function ExportPanel({
  isProcessing = false,
  canReturnToAstroDex = false,
  astrodexObjectName = null,
  astrodexReturning = false,
  astrodexReturned = false,
  astrodexError = null,
  defaultFilename = '',
  resultUrl,
  touchedSteps = [],
  onDownload,
  onReturnToAstroDex,
  onSaveAsPreset,
}: ExportPanelProps) {
  const { t } = useTranslation();
  const [filename, setFilename] = useState(defaultFilename);

  const trimmed = filename.trim();

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2.5">
        <CheckCircleIcon className="h-6 w-6 text-success" />
        <span className="flex flex-col">
          <span className="text-sm font-semibold text-ink">{t('export_panel.ready_title')}</span>
          <span className="text-xs text-faint">
            {touchedSteps.length > 0
              ? t('export_panel.recap', { steps: touchedSteps.join(', ') })
              : t('export_panel.recap_none')}
          </span>
        </span>
      </div>
      {resultUrl && (
        <div className="panel-inset overflow-hidden bg-black p-0">
          <img
            src={resultUrl}
            alt={t('export_panel.result_alt')}
            className="mx-auto max-h-48 w-full object-contain"
            draggable={false}
          />
        </div>
      )}
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
      <div className="flex flex-col gap-2">
        <button
          type="button"
          className="btn btn-primary w-full py-2.5 text-[15px]"
          disabled={isProcessing || trimmed === ''}
          onClick={() => onDownload(trimmed || defaultFilename)}
        >
          <DownloadIcon className="h-5 w-5" />
          {t('export_panel.download')}
        </button>
        {canReturnToAstroDex && (
          <button
            type="button"
            className="btn btn-amber w-full"
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
        className="btn btn-ghost btn-sm -ml-2 self-start"
        disabled={isProcessing}
        onClick={onSaveAsPreset}
      >
        {t('editor.save_as_preset')}
      </button>
    </div>
  );
}
