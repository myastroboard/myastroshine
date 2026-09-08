import { useEffect, useRef, useState, type DragEvent } from 'react';

import { useTranslation } from '@/hooks/useTranslation';

const ACCEPTED = [
  '.jpg',
  '.jpeg',
  '.png',
  '.tiff',
  '.tif',
  '.fits',
  '.fit',
  '.fts',
  '.cr2',
  '.cr3',
  '.nef',
  '.arw',
  '.dng',
  '.orf',
  '.rw2',
  '.pef',
  '.raf',
];
/** "48.2 MB" / "912 KB" - just enough to reassure the right file is going up. */
function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export interface ImageUploadProps {
  onUpload: (file: File) => void;
  isLoading?: boolean;
  /** Byte-transfer fraction (0-1) while uploading; null once the server is
   * decoding (shown as an indeterminate spinner). */
  progress?: number | null;
  /** The operator's configured upload cap (`GET /api/config`). */
  maxSizeMb?: number;
}

/** Drag-and-drop + file picker upload zone. */
export function ImageUpload({
  onUpload,
  isLoading = false,
  progress = null,
  maxSizeMb = 100,
}: ImageUploadProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [pending, setPending] = useState<File | null>(null);

  // Drop the remembered file once the upload settles (success or failure).
  useEffect(() => {
    if (!isLoading) {
      setPending(null);
    }
  }, [isLoading]);

  function validateAndUpload(file: File): void {
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    if (!ACCEPTED.includes(ext)) {
      setValidationError(t('image_upload.format_not_supported', { ext }));
      return;
    }
    if (file.size > maxSizeMb * 1024 * 1024) {
      setValidationError(t('image_upload.file_too_large', { mb: maxSizeMb }));
      return;
    }
    setValidationError(null);
    setPending(file);
    onUpload(file);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>): void {
    event.preventDefault();
    setDragActive(false);
    if (isLoading) {
      return;
    }
    const file = event.dataTransfer.files[0];
    if (file) {
      validateAndUpload(file);
    }
  }

  const percent = progress == null ? null : Math.round(progress * 100);

  return (
    <div className="mx-auto w-full max-w-xl">
      <div
        className={`dropzone ${dragActive && !isLoading ? 'dropzone-active' : ''}`}
        onDragOver={(event) => {
          event.preventDefault();
          if (!isLoading) {
            setDragActive(true);
          }
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
      >
        {isLoading ? (
          <div
            className="flex w-full max-w-xs flex-col items-center gap-3 py-2"
            role="status"
            aria-live="polite"
          >
            <span className="h-7 w-7 animate-spin rounded-full border-2 border-line border-t-accent" />
            <p className="text-sm font-medium text-ink">
              {percent == null
                ? t('image_upload.processing')
                : t('image_upload.uploading_percent', { percent })}
            </p>
            {percent != null && (
              <span className="h-1 w-full overflow-hidden rounded-full bg-line">
                <span
                  className="block h-full rounded-full bg-accent transition-[width] duration-150 ease-out"
                  style={{ width: `${percent}%` }}
                />
              </span>
            )}
            {pending && (
              <p className="max-w-full truncate text-xs text-faint">
                {pending.name} &middot; {formatBytes(pending.size)}
              </p>
            )}
          </div>
        ) : (
          <>
            <div className="grid h-12 w-12 place-items-center rounded-full border border-line bg-raised">
              <svg viewBox="0 0 24 24" className="h-5 w-5 stroke-muted" fill="none" aria-hidden>
                <path
                  d="M12 16V4m0 0-4 4m4-4 4 4M5 20h14"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <div className="flex flex-col gap-1">
              <p className="text-sm text-ink">{t('image_upload.drop_hint')}</p>
              <p className="text-xs text-faint">{t('image_upload.choose_file_hint')}</p>
            </div>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => inputRef.current?.click()}
            >
              {t('image_upload.choose_file_button')}
            </button>
            <p className="text-[11px] text-ghost">
              {t('image_upload.accepted_formats')} &middot;{' '}
              {t('image_upload.max_size', { mb: maxSizeMb })}
            </p>
            {validationError && <p className="text-xs text-danger">{validationError}</p>}
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED.join(',')}
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) {
              validateAndUpload(file);
            }
          }}
        />
      </div>
    </div>
  );
}
