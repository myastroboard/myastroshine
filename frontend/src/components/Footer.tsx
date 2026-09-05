import { useState } from 'react';

import { WhatsNewModal } from '@/components/WhatsNewModal';
import { useTranslation } from '@/hooks/useTranslation';
import { useVersionCheck } from '@/hooks/useVersionCheck';

const GITHUB_URL = 'https://github.com/myastroboard/myastroshine';

/**
 * Permanent page footer (name + version + GitHub link), inspired by
 * MyAstroBoard's own footer bar. Folds in the update-available notice - a
 * discreet second line, plus a "What's new" that opens the release notes in
 * a modal - once a newer release is confirmed available.
 */
export function Footer() {
  const { t } = useTranslation();
  const { updateAvailable, result } = useVersionCheck();
  const [showWhatsNew, setShowWhatsNew] = useState(false);
  const version = import.meta.env.VITE_APP_VERSION ?? '0.0.0-dev';
  const appName = import.meta.env.VITE_APP_NAME ?? 'MyAstroShine';

  return (
    <footer className="border-t border-hairline bg-canvas/95 px-4 py-3 text-xs text-faint backdrop-blur-md sm:px-6">
      <div className="mx-auto flex max-w-[1200px] flex-col gap-1.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span>
            {appName} &middot; v{version}
          </span>
          <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="hover:text-muted">
            GitHub
          </a>
        </div>

        {updateAvailable && result?.latestVersion && (
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
            {result.releaseNotes && (
              <button
                type="button"
                className="text-faint underline-offset-2 hover:text-muted hover:underline"
                onClick={() => setShowWhatsNew(true)}
              >
                {t('update_banner.whats_new')}
              </button>
            )}
          </div>
        )}
      </div>

      {showWhatsNew && result?.releaseNotes && (
        <WhatsNewModal
          releaseName={result.releaseName ?? result.latestVersion ?? ''}
          releaseNotes={result.releaseNotes}
          releaseUrl={result.releaseUrl}
          onClose={() => setShowWhatsNew(false)}
        />
      )}
    </footer>
  );
}
