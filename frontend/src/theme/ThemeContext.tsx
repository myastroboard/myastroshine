import { useEffect, useMemo, useState, type ReactNode } from 'react';

import { THEME_STORAGE_KEY } from '@/theme/config';
import {
  DARK_MEDIA_QUERY,
  ThemeContext,
  applyResolvedTheme,
  detectThemePreference,
  resolveTheme,
  type ThemeContextValue,
} from '@/theme/context';

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState(detectThemePreference);
  const resolved = resolveTheme(preference);

  // Apply on mount and whenever the resolved theme changes.
  useEffect(() => {
    applyResolvedTheme(resolved);
  }, [resolved]);

  // While following the OS, re-apply when the OS flips light/dark.
  useEffect(() => {
    if (preference !== 'system') {
      return;
    }
    let media: MediaQueryList;
    try {
      media = window.matchMedia(DARK_MEDIA_QUERY);
    } catch {
      return;
    }
    const onChange = () => applyResolvedTheme(resolveTheme('system'));
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, [preference]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      preference,
      resolved,
      setPreference: (next) => {
        setPreferenceState(next);
        try {
          window.localStorage.setItem(THEME_STORAGE_KEY, next);
        } catch {
          // per-viewer convenience only - a failed write just means the choice
          // won't survive a reload.
        }
      },
    }),
    [preference, resolved],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
