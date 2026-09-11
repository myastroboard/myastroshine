import { createContext } from 'react';

import de from '@/i18n/translations/de.json';
import en from '@/i18n/translations/en.json';
import es from '@/i18n/translations/es.json';
import fr from '@/i18n/translations/fr.json';
import it from '@/i18n/translations/it.json';
import pt from '@/i18n/translations/pt.json';
import { DEFAULT_LANGUAGE, LANGUAGE_STORAGE_KEY, isSupportedLanguage, type Language } from '@/i18n/config';

type TranslationTree = { [key: string]: string | TranslationTree };

const TRANSLATIONS: Record<Language, TranslationTree> = { de, en, es, fr, it, pt };

export const HTML_LANG: Record<Language, string> = { de: 'de', en: 'en', es: 'es', fr: 'fr', it: 'it', pt: 'pt' };

function resolve(tree: TranslationTree, key: string): string | undefined {
  let current: TranslationTree | string = tree;
  for (const part of key.split('.')) {
    if (typeof current !== 'object' || !(part in current)) {
      return undefined;
    }
    current = current[part];
  }
  return typeof current === 'string' ? current : undefined;
}

function interpolate(text: string, params?: Record<string, string | number>): string {
  if (!params) {
    return text;
  }
  return Object.entries(params).reduce(
    (result, [key, value]) => result.replaceAll(`{${key}}`, String(value)),
    text,
  );
}

export function translate(language: Language, key: string, params?: Record<string, string | number>): string {
  const value = resolve(TRANSLATIONS[language], key) ?? resolve(TRANSLATIONS[DEFAULT_LANGUAGE], key);
  return interpolate(value ?? key, params);
}

export function detectLanguage(): Language {
  try {
    const stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (stored && isSupportedLanguage(stored)) {
      return stored;
    }
  } catch {
    // localStorage unavailable (private mode, disabled site data) - fall through.
  }
  const browserLanguage = window.navigator.language.split('-')[0];
  return isSupportedLanguage(browserLanguage) ? browserLanguage : DEFAULT_LANGUAGE;
}

export interface I18nContextValue {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: string, params?: Record<string, string | number>) => string;
}

export const I18nContext = createContext<I18nContextValue>({
  language: DEFAULT_LANGUAGE,
  setLanguage: () => {},
  t: (key, params) => translate(DEFAULT_LANGUAGE, key, params),
});
