import { useRef, useState, type DragEvent } from 'react';

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
const MAX_SIZE_BYTES = 100 * 1024 * 1024;

export interface ImageUploadProps {
  onUpload: (file: File) => void;
  isLoading?: boolean;
}

/** Drag-and-drop + file picker upload zone. */
export function ImageUpload({ onUpload, isLoading = false }: ImageUploadProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  function validateAndUpload(file: File): void {
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    if (!ACCEPTED.includes(ext)) {
      setValidationError(t('image_upload.format_not_supported', { ext }));
      return;
    }
    if (file.size > MAX_SIZE_BYTES) {
      setValidationError(t('image_upload.file_too_large'));
      return;
    }
    setValidationError(null);
    onUpload(file);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>): void {
    event.preventDefault();
    setDragActive(false);
    const file = event.dataTransfer.files[0];
    if (file) {
      validateAndUpload(file);
    }
  }

  return (
    <div className="mx-auto w-full max-w-xl">
      <div
        className={`dropzone ${dragActive ? 'dropzone-active' : ''}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
      >
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
          disabled={isLoading}
          onClick={() => inputRef.current?.click()}
        >
          {isLoading ? t('image_upload.uploading_button') : t('image_upload.choose_file_button')}
        </button>
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
        <p className="text-[11px] text-ghost">{t('image_upload.accepted_formats')}</p>
        {validationError && <p className="text-xs text-danger">{validationError}</p>}
      </div>
    </div>
  );
}
