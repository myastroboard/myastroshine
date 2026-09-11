import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { ThemeSwitcher } from '@/components/ThemeSwitcher';
import { THEME_STORAGE_KEY } from '@/theme/config';
import { ThemeProvider } from '@/theme/ThemeContext';

describe('ThemeSwitcher', () => {
  afterEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove('dark');
  });

  it('defaults to System and offers all three options', () => {
    render(
      <ThemeProvider>
        <ThemeSwitcher />
      </ThemeProvider>,
    );

    const select = screen.getByRole('combobox', { name: 'Theme' });
    expect(select).toHaveValue('system');
    expect(screen.getByRole('option', { name: 'Light' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Dark' })).toBeInTheDocument();
  });

  it('switches to Dark, applies the class, and persists the choice', () => {
    render(
      <ThemeProvider>
        <ThemeSwitcher />
      </ThemeProvider>,
    );

    fireEvent.change(screen.getByRole('combobox', { name: 'Theme' }), {
      target: { value: 'dark' },
    });

    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });

  it('ignores a change event carrying an unsupported preference', () => {
    render(
      <ThemeProvider>
        <ThemeSwitcher />
      </ThemeProvider>,
    );

    const select = screen.getByRole('combobox', { name: 'Theme' });
    // Setting a <select>'s value to something with no matching <option> leaves
    // it unselected (value reads back as ''), which is itself unsupported -
    // this exercises the guard's false branch without needing to bypass the DOM.
    fireEvent.change(select, { target: { value: 'zz' } });

    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
    expect(select).toHaveValue('system');
  });
});
