export type EditorMode = 'single' | 'stack';

export interface StackModeProps {
  mode: EditorMode;
  onModeChange: (mode: EditorMode) => void;
}

const MODES: { value: EditorMode; label: string }[] = [
  { value: 'single', label: 'Single Image' },
  { value: 'stack', label: 'Multi-Image Stack' },
];

/** Mode selector: single-image enhancement vs multi-frame stacking (v1.1+). */
export function StackMode({ mode, onModeChange }: StackModeProps) {
  return (
    <div className="segmented self-start">
      {MODES.map((entry) => {
        const active = mode === entry.value;
        return (
          <button
            key={entry.value}
            type="button"
            aria-pressed={active}
            className={`segmented-item ${active ? 'segmented-item-active' : ''}`}
            onClick={() => onModeChange(entry.value)}
          >
            {entry.label}
          </button>
        );
      })}
    </div>
  );
}
