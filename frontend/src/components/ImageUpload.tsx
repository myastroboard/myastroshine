import { useRef, useState, type DragEvent } from 'react';

const ACCEPTED = ['.jpg', '.jpeg', '.png', '.tiff'];
const MAX_SIZE_BYTES = 100 * 1024 * 1024;

export interface ImageUploadProps {
  onUpload: (file: File) => void;
  isLoading?: boolean;
}

/** Drag-and-drop + file picker upload zone. */
export function ImageUpload({ onUpload, isLoading = false }: ImageUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  function validateAndUpload(file: File): void {
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    if (!ACCEPTED.includes(ext)) {
      setValidationError(`Format ${ext} not supported`);
      return;
    }
    if (file.size > MAX_SIZE_BYTES) {
      setValidationError('File size exceeds 100MB limit');
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
    <div
      className={`mx-auto flex max-w-xl flex-col items-center gap-4 rounded-lg border-2 border-dashed p-12 text-center transition-colors ${
        dragActive ? 'border-primary bg-primary/10' : 'border-white/20'
      }`}
      onDragOver={(event) => {
        event.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={handleDrop}
    >
      <p className="text-sm text-gray-300">
        Drag an astronomical image here, or
      </p>
      <button
        type="button"
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium disabled:opacity-50"
        disabled={isLoading}
        onClick={() => inputRef.current?.click()}
      >
        {isLoading ? 'Uploading...' : 'Choose a file'}
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
      <p className="text-xs text-gray-500">JPEG, PNG or TIFF, up to 100 MB</p>
      {validationError && <p className="text-xs text-red-300">{validationError}</p>}
    </div>
  );
}
