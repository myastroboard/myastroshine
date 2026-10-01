import type { ComponentType } from 'react';

import { MonitorIcon, MoonIcon, SunIcon, type IconProps } from '@/components/icons';
import { useTranslation } from '@/hooks/useTranslation';
import { useTheme } from '@/hooks/useTheme';
import { THEME_PREFERENCES, type ThemePreference } from '@/theme/config';

const THEME_ICONS: Record<ThemePreference, ComponentType<IconProps>> = {
  system: MonitorIcon,
  light: SunIcon,
  dark: MoonIcon,
};

/** Compact System/Light/Dark icon toggle, persisted client-side only. */
export function ThemeSwitcher() {
  const { t } = useTranslation();
  const { preference, setPreference } = useTheme();

  return (
    <div className="segmented p-0.5" role="radiogroup" aria-label={t('theme_switcher.aria_label')}>
      {THEME_PREFERENCES.map((value) => {
        const Icon = THEME_ICONS[value];
        const active = preference === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={t(`theme_switcher.${value}`)}
            title={t(`theme_switcher.${value}`)}
            className={`segmented-item grid place-items-center px-2 py-1 ${active ? 'segmented-item-active' : ''}`}
            onClick={() => setPreference(value)}
          >
            <Icon className="h-3.5 w-3.5" />
          </button>
        );
      })}
    </div>
  );
}
