import { SUPPORTED_LANGUAGES, isSupportedLanguage } from '@/i18n/config';
import { useTranslation } from '@/hooks/useTranslation';

const LANGUAGE_CODE_LABEL: Record<string, string> = { en: 'EN', fr: 'FR' };

/** Compact EN/FR select, persisted client-side only - not part of `AppSettings`. */
export function LanguageSwitcher() {
  const { language, setLanguage, t } = useTranslation();

  return (
    <select
      className="field w-16 py-1.5 text-xs"
      aria-label={t('language_switcher.aria_label')}
      value={language}
      onChange={(event) => {
        const next = event.target.value;
        if (isSupportedLanguage(next)) {
          setLanguage(next);
        }
      }}
    >
      {SUPPORTED_LANGUAGES.map((code) => (
        <option key={code} value={code}>
          {LANGUAGE_CODE_LABEL[code]}
        </option>
      ))}
    </select>
  );
}
