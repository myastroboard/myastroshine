import { useState } from 'react';

export interface SavePresetDialogProps {
  onSave: (name: string, description: string) => Promise<void> | void;
  onClose: () => void;
}

/** Small modal that collects a name for a user preset. */
export function SavePresetDialog({ onSave, onClose }: SavePresetDialogProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(): Promise<void> {
    if (!name.trim()) {
      setError('A name is required');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSave(name.trim(), description.trim());
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the preset');
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Save as preset"
    >
      <div className="flex w-full max-w-sm flex-col gap-4 rounded-xl border border-line bg-overlay p-5 shadow-pop">
        <h2 className="text-sm font-semibold text-ink">Save as preset</h2>
        <label className="flex flex-col gap-1.5">
          <span className="label">Name</span>
          <input
            className="field"
            placeholder="My nebula look"
            value={name}
            autoFocus
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="label">Description (optional)</span>
          <input
            className="field"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </label>
        {error && <p className="text-xs text-danger">{error}</p>}
        <div className="mt-1 flex justify-end gap-2">
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={busy}
            onClick={() => void handleSubmit()}
          >
            {busy ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
