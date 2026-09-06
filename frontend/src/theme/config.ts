export const THEME_PREFERENCES = ['system', 'light', 'dark'] as const;

/** What the viewer picked in the footer Theme control. */
export type ThemePreference = (typeof THEME_PREFERENCES)[number];

/** The theme actually applied to <html> once `system` is resolved. */
export type ResolvedTheme = 'light' | 'dark';

export const DEFAULT_THEME_PREFERENCE: ThemePreference = 'system';

export const THEME_STORAGE_KEY = 'myastroshine_theme';

export function isThemePreference(value: string): value is ThemePreference {
  return (THEME_PREFERENCES as readonly string[]).includes(value);
}
