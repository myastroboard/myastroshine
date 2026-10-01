import { useRef, useState } from 'react';

import { PhotoStackIcon } from '@/components/icons';
import { useTranslation } from '@/hooks/useTranslation';

const ACCEPT =
  '.jpg,.jpeg,.png,.tiff,.tif,.fits,.fit,.fts,.cr2,.cr3,.nef,.arw,.dng,.orf,.rw2,.pef,.raf';

export interface StackUploadZoneProps {
  /** Compact "add more" affordance vs the full empty-state dropzone. */
  compact: boolean;
  maxSizeMb?: number;
  onAddFiles: (files: File[]) => void;
}

/** Drag-and-drop / file picker for stacking frames. */
export function StackUploadZone({ compact, maxSizeMb = 100, onAddFiles }: StackUploadZoneProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);

  const input = (
    <input
      ref={inputRef}
      type="file"
      multiple
      accept={ACCEPT}
      className="hidden"
      onChange={(event) => onAddFiles(Array.from(event.target.files ?? []))}
    />
  );

  if (compact) {
    return (
      <label className="chip cursor-pointer self-start">
        <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 stroke-current" fill="none" aria-hidden>
          <path d="M12 5v14M5 12h14" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        {t('stacking.upload_zone.add_frames')}
        {input}
      </label>
    );
  }

  return (
    <div
      className={`dropzone h-full ${dragActive ? 'dropzone-active' : ''}`}
      onDragOver={(event) => {
        event.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragActive(false);
        onAddFiles(Array.from(event.dataTransfer.files));
      }}
    >
      <div className="grid h-14 w-14 place-items-center rounded-full border border-line bg-raised text-accent">
        <PhotoStackIcon className="h-7 w-7" />
      </div>
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-ink">{t('stacking.upload_zone.title')}</h2>
        <p className="text-sm text-muted">{t('stacking.upload_zone.subtitle')}</p>
      </div>
      <button type="button" className="btn btn-outline" onClick={() => inputRef.current?.click()}>
        {t('stacking.upload_zone.choose_files_button')}
      </button>
      <p className="text-xs text-faint">{t('stacking.upload_zone.drop_hint')}</p>
      <p className="mt-auto text-[11px] text-faint">
        {t('stacking.upload_zone.accepted_formats')} &middot;{' '}
        {t('stacking.upload_zone.max_size', { mb: maxSizeMb })}
      </p>
      {input}
    </div>
  );
}
