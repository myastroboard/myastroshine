import { useState, type CSSProperties } from 'react';

import { useTranslation } from '@/hooks/useTranslation';
import type { LookCatalog, LookId, LookParameters, LookScene } from '@/types';

export interface StylePanelProps {
  look: LookParameters;
  /** The session's looks, grouped by kind of picture (`GET /api/looks/{id}`). */
  catalog: LookCatalog;
  /** The group a built-in preset the user applied points at, if any. */
  suggestedScene?: LookScene | null;
  /** URL of a gallery thumbnail: the edit before its look, with `look` applied. */
  thumbnailUrl: (look: LookId | null) => string;
  onLookChange: <K extends keyof LookParameters>(key: K, value: LookParameters[K]) => void;
  isProcessing: boolean;
}

/** The group the gallery shows: the user's pick, else the chosen look's group,
 * else a night landscape (the photo's own sky mask says so), else the group of
 * the preset they applied, else the catalogue's default - always one the
 * catalogue has. */
function shownScene(
  catalog: LookCatalog,
  picked: LookScene | null,
  lookId: LookId | null,
  suggested: LookScene | null,
): LookScene {
  const scenes = catalog.groups.map((group) => group.scene);
  const ofLook = catalog.groups.find((group) => lookId !== null && group.looks.includes(lookId));
  const night = catalog.scene === 'nightscape' ? catalog.scene : null;
  const wanted = picked ?? ofLook?.scene ?? night ?? suggested ?? catalog.scene;
  return scenes.includes(wanted) ? wanted : (scenes[0] ?? catalog.scene);
}

/**
 * The "Style" step: a gallery of the user's own image in each finishing look,
 * plus one "how much" slider for the chosen look. Looks are grouped by kind of
 * picture (any image, night landscape, nebula, galaxy, star cluster); a row of
 * chips switches group - the kind of a deep-sky target is not guessed. Every
 * look only reworks the recorded light (backend `app/services/looks.py`).
 */
export function StylePanel({
  look,
  catalog,
  suggestedScene = null,
  thumbnailUrl,
  onLookChange,
  isProcessing,
}: StylePanelProps) {
  const { t } = useTranslation();
  const [picked, setPicked] = useState<LookScene | null>(null);
  const selected = look.lookId;
  const scene = shownScene(catalog, picked, selected, suggestedScene);
  const group = catalog.groups.find((entry) => entry.scene === scene);
  // "No style" is always the first choice.
  const choices: (LookId | null)[] = [null, ...(group?.looks ?? [])];
  const nameOf = (id: LookId | null) =>
    id === null ? t('style_panel.none.name') : t(`style_panel.looks.${id}.name`);
  // Slider fill from 0 to the current amount (a per-instance runtime value).
  const fill = {
    '--fill-from': 0,
    '--fill-to': look.amount / 100,
  } as CSSProperties;

  return (
    <div className="flex flex-col gap-4">
      {catalog.groups.length > 1 && (
        <div
          className="flex flex-wrap gap-1"
          role="radiogroup"
          aria-label={t('style_panel.scenes_aria')}
        >
          {catalog.groups.map((entry) => (
            <button
              key={entry.scene}
              type="button"
              role="radio"
              aria-checked={entry.scene === scene}
              className={`chip ${entry.scene === scene ? 'chip-active' : ''}`}
              onClick={() => setPicked(entry.scene)}
            >
              {t(`style_panel.scenes.${entry.scene}`)}
            </button>
          ))}
        </div>
      )}
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
        {selected === null ? t('style_panel.none.hint') : t(`style_panel.looks.${selected}.hint`)}
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
