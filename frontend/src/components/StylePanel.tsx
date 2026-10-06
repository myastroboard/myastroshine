import type { CSSProperties } from 'react';

import { useTranslation } from '@/hooks/useTranslation';
import type { LookId, LookParameters, LookScene } from '@/types';

export interface StylePanelProps {
  look: LookParameters;
  /** The looks to offer, in order (from the session's look catalogue). */
  looks: LookId[];
  /** `'nightscape'`: the photo has a landscape - say the first looks use it. */
  scene: LookScene;
  /** URL of a gallery thumbnail: the edit before its look, with `look` applied. */
  thumbnailUrl: (look: LookId | null) => string;
  onLookChange: <K extends keyof LookParameters>(key: K, value: LookParameters[K]) => void;
  isProcessing: boolean;
}

/**
 * The "Style" step: a gallery of the user's own image in each finishing look,
 * plus one "how much" slider for the chosen look. Every look only reworks the
 * recorded light (see backend `app/services/looks.py`) - no added detail.
 */
export function StylePanel({
  look,
  looks,
  scene,
  thumbnailUrl,
  onLookChange,
  isProcessing,
}: StylePanelProps) {
  const { t } = useTranslation();
  const selected = look.lookId;
  // "No style" is always the first choice.
  const choices: (LookId | null)[] = [null, ...looks];
  const nameOf = (id: LookId | null) =>
    id === null ? t('style_panel.none.name') : t(`style_panel.looks.${id}.name`);
  // Slider fill from 0 to the current amount (a per-instance runtime value).
  const fill = { '--fill-from': 0, '--fill-to': look.amount / 100 } as CSSProperties;

  return (
    <div className="flex flex-col gap-4">
      {scene === 'nightscape' && (
        <p className="panel-inset text-xs text-muted">{t('style_panel.nightscape_note')}</p>
      )}
      <div
        className="grid grid-cols-2 gap-2"
        role="radiogroup"
        aria-label={t('style_panel.gallery_aria')}
      >
        {choices.map((id) => {
          const active = id === selected;
          return (
            <button
              key={id ?? 'none'}
              type="button"
              role="radio"
              aria-checked={active}
              disabled={isProcessing}
              className={`option-card flex-col gap-1.5 p-1.5 ${active ? 'option-card-active' : ''}`}
              onClick={() => onLookChange('lookId', id)}
            >
              <img
                src={thumbnailUrl(id)}
                alt=""
                loading="lazy"
                className="aspect-[4/3] w-full rounded-md bg-raised object-cover"
              />
              <span className="px-1 text-xs font-medium text-ink">{nameOf(id)}</span>
            </button>
          );
        })}
      </div>

      <p className="text-xs text-faint" aria-live="polite">
        {selected === null
          ? t('style_panel.none.hint')
          : t(`style_panel.looks.${selected}.hint`)}
      </p>

      {selected !== null && (
        <div className="flex flex-col gap-1.5 text-sm">
          <span className="flex items-baseline justify-between">
            <label htmlFor="style-amount" className="text-muted">
              {t('style_panel.amount.label')}
            </label>
            <span className="text-xs tabular-nums text-faint">{look.amount}</span>
          </span>
          <input
            id="style-amount"
            type="range"
            className="slider"
            style={fill}
            min={0}
            max={100}
            step={1}
            value={look.amount}
            disabled={isProcessing}
            onChange={(event) => onLookChange('amount', Number(event.target.value))}
          />
          <p className="text-xs text-faint">{t('style_panel.amount.hint')}</p>
        </div>
      )}

      <p className="text-[11px] text-faint">{t('style_panel.honest_note')}</p>
    </div>
  );
}
