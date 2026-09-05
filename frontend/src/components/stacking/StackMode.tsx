import { useTranslation } from '@/hooks/useTranslation';

export type EditorMode = 'single' | 'stack';

export interface StackModeProps {
  mode: EditorMode;
  onModeChange: (mode: EditorMode) => void;
}

const MODE_KEYS: { value: EditorMode; key: string }[] = [
  { value: 'single', key: 'stacking.mode.single' },
  { value: 'stack', key: 'stacking.mode.stack' },
];

/** Mode selector: single-image enhancement vs multi-frame stacking (v1.1+). */
export function StackMode({ mode, onModeChange }: StackModeProps) {
  const { t } = useTranslation();
  return (
    <div className="segmented self-start">
      {MODE_KEYS.map((entry) => {
        const active = mode === entry.value;
        return (
          <button
            key={entry.value}
            type="button"
            aria-pressed={active}
            className={`segmented-item ${active ? 'segmented-item-active' : ''}`}
            onClick={() => onModeChange(entry.value)}
          >
            {t(entry.key)}
          </button>
        );
      })}
    </div>
  );
}
