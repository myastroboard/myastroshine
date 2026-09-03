export interface StackFrame {
  index: number;
  name: string;
  sizeBytes: number;
  status: 'queued' | 'uploading' | 'done' | 'error';
  progress: number;
}

export interface StackUploadZoneProps {
  frames: StackFrame[];
  onAddFiles: (files: File[]) => void;
}

/** Multi-frame drag-and-drop upload list (v1.1+). */
export function StackUploadZone({ frames, onAddFiles }: StackUploadZoneProps) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border-2 border-dashed border-white/20 p-6">
      <label className="text-sm">
        Add frames
        <input
          type="file"
          multiple
          accept=".jpg,.jpeg,.png,.tiff"
          className="mt-2 block text-xs"
          onChange={(event) => onAddFiles(Array.from(event.target.files ?? []))}
        />
      </label>
      <ul className="flex flex-col gap-1 text-xs">
        {frames.map((frame) => (
          <li key={frame.index} className="flex justify-between">
            <span>
              Frame {frame.index + 1}: {frame.name}
            </span>
            <span className="text-gray-400">{frame.status}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
