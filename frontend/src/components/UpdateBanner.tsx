import { useTranslation } from '@/hooks/useTranslation';
import { useVersionCheck } from '@/hooks/useVersionCheck';

/** Discreet footer banner, shown only once a newer release is confirmed available. */
export function UpdateBanner() {
  const { t } = useTranslation();
  const { updateAvailable, result } = useVersionCheck();

  if (!updateAvailable || !result?.latestVersion) {
    return null;
  }

  return (
    <footer className="sticky bottom-0 z-30 border-t border-hairline bg-canvas/95 px-4 py-2 text-xs backdrop-blur-md sm:px-6">
      <div className="mx-auto flex max-w-[1200px] flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-2 text-muted">
          <span>{t('update_banner.available', { version: result.latestVersion })}</span>
          {result.releaseUrl && (
            <a
              href={result.releaseUrl}
              target="_blank"
              rel="noreferrer"
              className="font-medium text-accent hover:underline"
            >
              {t('update_banner.view_on_github')}
            </a>
          )}
        </div>
        {result.releaseNotes && (
          <details>
            <summary className="cursor-pointer text-faint hover:text-muted">
              {t('update_banner.whats_new')}
            </summary>
            <p className="mt-1.5 max-h-40 overflow-auto whitespace-pre-line text-faint">
              {result.releaseNotes}
            </p>
          </details>
        )}
      </div>
    </footer>
  );
}
