import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import Markdown from 'markdown-to-jsx';

import { useTranslation } from '@/hooks/useTranslation';

export interface WhatsNewModalProps {
  releaseName: string;
  releaseNotes: string;
  releaseUrl: string | null;
  onClose: () => void;
}

/**
 * Modal showing a GitHub release's notes, rendered from markdown (never as
 * raw HTML). Portaled to `document.body` - it's opened from the footer,
 * which has `backdrop-blur` (a `backdrop-filter`, like `transform` or
 * `will-change`, creates a new containing block for `position: fixed`
 * descendants), so without a portal the modal would be trapped inside the
 * footer's box instead of covering the viewport.
 */
export function WhatsNewModal({ releaseName, releaseNotes, releaseUrl, onClose }: WhatsNewModalProps) {
  const { t } = useTranslation();

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return createPortal(
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={releaseName}
      onClick={(event) => event.target === event.currentTarget && onClose()}
    >
      <div className="flex w-full max-w-2xl flex-col gap-4 rounded-xl border border-line bg-overlay p-5 shadow-pop">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-ink">{releaseName}</h2>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>
            {t('common.close')}
          </button>
        </div>

        <div className="max-h-[60vh] overflow-y-auto overflow-x-hidden break-words text-sm text-muted [&_a]:text-accent [&_a]:underline [&_code]:whitespace-pre-wrap [&_code]:break-all [&_code]:rounded [&_code]:bg-raised [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-xs [&_h3]:mt-3 [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:text-ink [&_h3]:first:mt-0 [&_h4]:mt-2 [&_h4]:text-sm [&_h4]:font-medium [&_h4]:text-ink [&_li]:ml-4 [&_li]:list-disc [&_p]:mt-2 [&_p]:first:mt-0 [&_ul]:mt-1">
          <Markdown>{releaseNotes}</Markdown>
        </div>

        {releaseUrl && (
          <a
            href={releaseUrl}
            target="_blank"
            rel="noreferrer"
            className="text-xs font-medium text-accent hover:underline"
          >
            {t('update_banner.view_on_github')}
          </a>
        )}
      </div>
    </div>,
    document.body,
  );
}
