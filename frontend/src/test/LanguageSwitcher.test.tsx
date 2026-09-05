import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { LANGUAGE_STORAGE_KEY } from '@/i18n/config';
import { I18nProvider } from '@/i18n/I18nContext';

describe('LanguageSwitcher', () => {
  afterEach(() => {
    localStorage.clear();
  });

  it('defaults to English and offers both supported languages', () => {
    render(
      <I18nProvider>
        <LanguageSwitcher />
      </I18nProvider>,
    );

    const select = screen.getByRole('combobox', { name: 'Language' });
    expect(select).toHaveValue('en');
    expect(screen.getByRole('option', { name: 'FR' })).toBeInTheDocument();
  });

  it('switches to French and persists the choice', () => {
    render(
      <I18nProvider>
        <LanguageSwitcher />
      </I18nProvider>,
    );

    fireEvent.change(screen.getByRole('combobox', { name: 'Language' }), {
      target: { value: 'fr' },
    });

    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('fr');
  });
});
