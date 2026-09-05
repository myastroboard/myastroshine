import { useEffect, useMemo, useState, type ReactNode } from 'react';

import { LANGUAGE_STORAGE_KEY, type Language } from '@/i18n/config';
import { HTML_LANG, I18nContext, translate, detectLanguage, type I18nContextValue } from '@/i18n/context';

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(detectLanguage);

  useEffect(() => {
    document.documentElement.lang = HTML_LANG[language];
  }, [language]);

  const value = useMemo<I18nContextValue>(
    () => ({
      language,
      setLanguage: (next) => {
        setLanguageState(next);
        try {
          window.localStorage.setItem(LANGUAGE_STORAGE_KEY, next);
        } catch {
          // per-viewer convenience only - a failed write just means the choice
          // won't survive a reload.
        }
      },
      t: (key, params) => translate(language, key, params),
    }),
    [language],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
