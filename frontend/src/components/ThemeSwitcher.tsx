import { useTranslation } from '@/hooks/useTranslation';
import { useTheme } from '@/hooks/useTheme';
import { THEME_PREFERENCES, isThemePreference } from '@/theme/config';

/** Compact System/Light/Dark select, persisted client-side only. */
export function ThemeSwitcher() {
  const { t } = useTranslation();
  const { preference, setPreference } = useTheme();

  return (
    <select
      className="field w-auto py-1.5 text-xs"
      aria-label={t('theme_switcher.aria_label')}
      value={preference}
      onChange={(event) => {
        const next = event.target.value;
        if (isThemePreference(next)) {
          setPreference(next);
        }
      }}
    >
      {THEME_PREFERENCES.map((value) => (
        <option key={value} value={value}>
          {t(`theme_switcher.${value}`)}
        </option>
      ))}
    </select>
  );
}
