import { render, screen, fireEvent } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { THEME_STORAGE_KEY } from '@/theme/config';
import { detectThemePreference, prefersDark, resolveTheme } from '@/theme/context';
import { ThemeProvider } from '@/theme/ThemeContext';
import { useTheme } from '@/hooks/useTheme';

let lastMediaListeners: Array<() => void> = [];

function mockMatchMedia(matches: boolean, { resetListeners = true } = {}): void {
  if (resetListeners) {
    lastMediaListeners = [];
  }
  window.matchMedia = ((query: string) => ({
    matches,
    media: query,
    onchange: null,
    addEventListener: (_type: string, listener: () => void) => {
      lastMediaListeners.push(listener);
    },
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

function Probe() {
  const { preference, resolved, setPreference } = useTheme();
  return (
    <div>
      <span data-testid="preference">{preference}</span>
      <span data-testid="resolved">{resolved}</span>
      <button type="button" onClick={() => setPreference('dark')}>
        go dark
      </button>
      <button type="button" onClick={() => setPreference('system')}>
        go system
      </button>
    </div>
  );
}

describe('theme', () => {
  beforeEach(() => {
    mockMatchMedia(false);
  });

  afterEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove('dark');
    vi.restoreAllMocks();
  });

  describe('detectThemePreference', () => {
    it('defaults to system when nothing is stored', () => {
      expect(detectThemePreference()).toBe('system');
    });

    it('returns a stored preference', () => {
      localStorage.setItem(THEME_STORAGE_KEY, 'dark');
      expect(detectThemePreference()).toBe('dark');
    });

    it('ignores an unrecognised stored value', () => {
      localStorage.setItem(THEME_STORAGE_KEY, 'sepia');
      expect(detectThemePreference()).toBe('system');
    });
  });

  describe('resolveTheme', () => {
    it('passes light/dark through unchanged', () => {
      expect(resolveTheme('light')).toBe('light');
      expect(resolveTheme('dark')).toBe('dark');
    });

    it('follows the OS when set to system', () => {
      mockMatchMedia(true);
      expect(resolveTheme('system')).toBe('dark');
      mockMatchMedia(false);
      expect(resolveTheme('system')).toBe('light');
    });
  });

  describe('prefersDark', () => {
    it('defaults to false when matchMedia throws (unsupported browser)', () => {
      window.matchMedia = (() => {
        throw new Error('matchMedia unsupported');
      }) as unknown as typeof window.matchMedia;

      expect(prefersDark()).toBe(false);
    });
  });

  describe('ThemeProvider', () => {
    it('defaults to system, resolving to light on a light OS', () => {
      render(
        <ThemeProvider>
          <Probe />
        </ThemeProvider>,
      );

      expect(screen.getByTestId('preference')).toHaveTextContent('system');
      expect(screen.getByTestId('resolved')).toHaveTextContent('light');
      expect(document.documentElement.classList.contains('dark')).toBe(false);
    });

    it('applies .dark when system resolves to a dark OS', () => {
      mockMatchMedia(true);

      render(
        <ThemeProvider>
          <Probe />
        </ThemeProvider>,
      );

      expect(screen.getByTestId('resolved')).toHaveTextContent('dark');
      expect(document.documentElement.classList.contains('dark')).toBe(true);
    });

    it('switches theme, toggles the class, and persists the choice', () => {
      render(
        <ThemeProvider>
          <Probe />
        </ThemeProvider>,
      );

      fireEvent.click(screen.getByRole('button', { name: 'go dark' }));

      expect(screen.getByTestId('preference')).toHaveTextContent('dark');
      expect(document.documentElement.classList.contains('dark')).toBe(true);
      expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');

      fireEvent.click(screen.getByRole('button', { name: 'go system' }));

      expect(document.documentElement.classList.contains('dark')).toBe(false);
      expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('system');
    });

    it('falls back to system defaults with no ThemeProvider', () => {
      render(<Probe />);

      expect(screen.getByTestId('preference')).toHaveTextContent('system');
      expect(screen.getByTestId('resolved')).toHaveTextContent('light');
    });

    it('the default context value is a harmless no-op setPreference', () => {
      render(<Probe />);
      // No ThemeProvider - the default context's setPreference does nothing.
      expect(() => fireEvent.click(screen.getByRole('button', { name: 'go dark' }))).not.toThrow();
      expect(screen.getByTestId('preference')).toHaveTextContent('system');
    });

    it('re-applies the resolved theme when the OS preference flips while following system', () => {
      mockMatchMedia(false);
      render(
        <ThemeProvider>
          <Probe />
        </ThemeProvider>,
      );
      expect(document.documentElement.classList.contains('dark')).toBe(false);

      // OS flips to dark; resolveTheme('system') will now read dark. Keep the
      // already-registered listener array so the mount-time subscription fires.
      mockMatchMedia(true, { resetListeners: false });
      lastMediaListeners.forEach((listener) => listener());

      expect(document.documentElement.classList.contains('dark')).toBe(true);
    });

    it('does not crash subscribing to OS changes when matchMedia throws', () => {
      window.matchMedia = (() => {
        throw new Error('matchMedia unsupported');
      }) as unknown as typeof window.matchMedia;

      render(
        <ThemeProvider>
          <Probe />
        </ThemeProvider>,
      );

      expect(screen.getByTestId('resolved')).toHaveTextContent('light');
    });

    it('setPreference still updates state when localStorage.setItem throws', () => {
      const setItem = vi
        .spyOn(Object.getPrototypeOf(window.localStorage) as Storage, 'setItem')
        .mockImplementation(() => {
          throw new Error('storage unavailable');
        });

      render(
        <ThemeProvider>
          <Probe />
        </ThemeProvider>,
      );

      fireEvent.click(screen.getByRole('button', { name: 'go dark' }));

      expect(screen.getByTestId('preference')).toHaveTextContent('dark');
      setItem.mockRestore();
    });
  });
});
