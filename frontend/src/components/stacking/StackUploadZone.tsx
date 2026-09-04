export interface StackFrame {
  index: number;
  name: string;
  sizeBytes: number;
  status: 'queued' | 'uploading' | 'done' | 'error';
  progress: number;
  file: File;
}

export interface StackUploadZoneProps {
  frames: StackFrame[];
  onAddFiles: (files: File[]) => void;
}

const STATUS_TONE: Record<StackFrame['status'], string> = {
  queued: 'text-faint',
  uploading: 'text-accent-strong',
  done: 'text-success',
  error: 'text-danger',
};

/** Multi-frame drag-and-drop upload list (v1.1+). */
export function StackUploadZone({ frames, onAddFiles }: StackUploadZoneProps) {
  return (
    <div className="flex flex-col gap-4">
      <label className="dropzone cursor-pointer">
        <div className="grid h-10 w-10 place-items-center rounded-full border border-line bg-raised">
          <svg viewBox="0 0 24 24" className="h-4 w-4 stroke-muted" fill="none" aria-hidden>
            <path
              d="M12 16V4m0 0-4 4m4-4 4 4M5 20h14"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-sm text-ink">Add frames</span>
          <span className="text-xs text-faint">Select multiple files at once</span>
        </div>
        <input
          type="file"
          multiple
          accept=".jpg,.jpeg,.png,.tiff"
          className="hidden"
          onChange={(event) => onAddFiles(Array.from(event.target.files ?? []))}
        />
      </label>

      {frames.length > 0 && (
        <ul className="flex flex-col divide-y divide-hairline rounded-lg border border-hairline bg-surface px-3 text-xs">
          {frames.map((frame) => (
            <li key={frame.index} className="flex items-center justify-between gap-3 py-2">
              <span className="truncate text-muted">
                <span className="text-faint">Frame {frame.index + 1}:</span> {frame.name}
              </span>
              <span className={`shrink-0 tabular-nums ${STATUS_TONE[frame.status]}`}>
                {frame.status}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
