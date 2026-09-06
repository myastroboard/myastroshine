import { createContext } from 'react';

import {
  DEFAULT_THEME_PREFERENCE,
  THEME_STORAGE_KEY,
  isThemePreference,
  type ResolvedTheme,
  type ThemePreference,
} from '@/theme/config';

/** The <html> pre-paint background per theme - keep in sync with index.html. */
const THEME_COLOR: Record<ResolvedTheme, string> = {
  light: '#eef2f5',
  dark: '#060b12',
};

export const DARK_MEDIA_QUERY = '(prefers-color-scheme: dark)';

/** The viewer's stored choice, or the default when nothing is stored. */
export function detectThemePreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored && isThemePreference(stored)) {
      return stored;
    }
  } catch {
    // localStorage unavailable (private mode, disabled site data) - fall through.
  }
  return DEFAULT_THEME_PREFERENCE;
}

/** Whether the OS currently asks for a dark UI. Safe when matchMedia is absent. */
export function prefersDark(): boolean {
  try {
    return window.matchMedia(DARK_MEDIA_QUERY).matches;
  } catch {
    return false;
  }
}

/** Collapse a preference to the theme that actually gets applied. */
export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  if (preference === 'system') {
    return prefersDark() ? 'dark' : 'light';
  }
  return preference;
}

/** Put the resolved theme on <html> and match the browser chrome colour. */
export function applyResolvedTheme(resolved: ResolvedTheme): void {
  document.documentElement.classList.toggle('dark', resolved === 'dark');

  let meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (!meta) {
    meta = document.createElement('meta');
    meta.name = 'theme-color';
    document.head.appendChild(meta);
  }
  meta.content = THEME_COLOR[resolved];
}

export interface ThemeContextValue {
  /** What the viewer picked: system, light, or dark. */
  preference: ThemePreference;
  /** The theme currently applied (system already resolved). */
  resolved: ResolvedTheme;
  setPreference: (preference: ThemePreference) => void;
}

export const ThemeContext = createContext<ThemeContextValue>({
  preference: DEFAULT_THEME_PREFERENCE,
  resolved: 'light',
  setPreference: () => {},
});
