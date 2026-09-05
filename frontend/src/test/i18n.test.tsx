import { render, screen, fireEvent } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { LANGUAGE_STORAGE_KEY } from '@/i18n/config';
import { I18nProvider } from '@/i18n/I18nContext';
import { useTranslation } from '@/hooks/useTranslation';

function Probe() {
  const { language, setLanguage, t } = useTranslation();
  return (
    <div>
      <span data-testid="language">{language}</span>
      <span data-testid="cancel">{t('common.cancel')}</span>
      <span data-testid="sources">{t('slider_panel.sources_count', { count: 7 })}</span>
      <span data-testid="missing">{t('nothing.here')}</span>
      <button type="button" onClick={() => setLanguage('fr')}>
        switch
      </button>
    </div>
  );
}

describe('i18n', () => {
  afterEach(() => {
    localStorage.clear();
  });

  it('falls back to English outside any I18nProvider', () => {
    render(<Probe />);

    expect(screen.getByTestId('language')).toHaveTextContent('en');
    expect(screen.getByTestId('cancel')).toHaveTextContent('Cancel');
  });

  it('interpolates placeholders', () => {
    render(<Probe />);

    expect(screen.getByTestId('sources')).toHaveTextContent('7 sources');
  });

  it('returns the key itself for a missing translation', () => {
    render(<Probe />);

    expect(screen.getByTestId('missing')).toHaveTextContent('nothing.here');
  });

  it('reads a stored language preference on mount', () => {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, 'fr');

    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );

    expect(screen.getByTestId('language')).toHaveTextContent('fr');
    expect(screen.getByTestId('cancel')).toHaveTextContent('Annuler');
  });

  it('switches language and persists the choice', () => {
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'switch' }));

    expect(screen.getByTestId('language')).toHaveTextContent('fr');
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('fr');
  });
});
