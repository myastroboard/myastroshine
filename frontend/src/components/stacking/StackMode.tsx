export type EditorMode = 'single' | 'stack';

export interface StackModeProps {
  mode: EditorMode;
  onModeChange: (mode: EditorMode) => void;
}

/** Mode selector: single-image enhancement vs multi-frame stacking (v1.1+). */
export function StackMode({ mode, onModeChange }: StackModeProps) {
  return (
    <div className="flex gap-2 rounded-lg border border-white/10 p-1 text-sm">
      <button
        type="button"
        className={`flex-1 rounded px-3 py-2 ${mode === 'single' ? 'bg-primary/20' : ''}`}
        onClick={() => onModeChange('single')}
      >
        Single Image
      </button>
      <button
        type="button"
        className={`flex-1 rounded px-3 py-2 ${mode === 'stack' ? 'bg-primary/20' : ''}`}
        onClick={() => onModeChange('stack')}
      >
        Multi-Image Stack
      </button>
    </div>
  );
}
