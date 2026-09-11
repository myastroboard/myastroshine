import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { Footer } from '@/components/Footer';
import { I18nProvider } from '@/i18n/I18nContext';
import { ThemeProvider } from '@/theme/ThemeContext';
import { apiClient } from '@/services/api';
import type { VersionCheckResult } from '@/types';

vi.mock('@/services/api', () => ({
  apiClient: { checkForUpdates: vi.fn() },
}));

const mocked = vi.mocked(apiClient);

function renderFooter() {
  return render(
    <ThemeProvider>
      <I18nProvider>
        <Footer />
      </I18nProvider>
    </ThemeProvider>,
  );
}

const BASE_RESULT: VersionCheckResult = {
  currentVersion: '1.0.0',
  latestVersion: null,
  updateAvailable: false,
  releaseUrl: null,
  releaseName: null,
  releaseNotes: null,
  publishedAt: null,
  error: null,
};

describe('Footer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove('dark');
    vi.unstubAllEnvs();
  });

  it('always shows the app name and a GitHub link', async () => {
    mocked.checkForUpdates.mockResolvedValue({ ...BASE_RESULT });
    renderFooter();

    expect(screen.getByText(/MyAstroShine/)).toBeInTheDocument();
    const link = screen.getByRole('link', { name: 'GitHub' });
    expect(link).toHaveAttribute('href', 'https://github.com/myastroboard/myastroshine');
    await waitFor(() => expect(mocked.checkForUpdates).toHaveBeenCalled());
  });

  it('carries the theme and language switchers', async () => {
    mocked.checkForUpdates.mockResolvedValue({ ...BASE_RESULT });
    renderFooter();

    expect(screen.getByRole('combobox', { name: 'Theme' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Language' })).toBeInTheDocument();
    await waitFor(() => expect(mocked.checkForUpdates).toHaveBeenCalled());
  });

  it('has no update notice when no update is available', async () => {
    mocked.checkForUpdates.mockResolvedValue({ ...BASE_RESULT });
    renderFooter();

    await waitFor(() => expect(mocked.checkForUpdates).toHaveBeenCalled());
    expect(screen.queryByText(/new version/i)).not.toBeInTheDocument();
  });

  it('folds in the update notice once available', async () => {
    mocked.checkForUpdates.mockResolvedValue({
      ...BASE_RESULT,
      latestVersion: '2.0.0',
      updateAvailable: true,
      releaseUrl: 'https://github.com/myastroboard/myastroshine/releases/tag/v2.0.0',
      releaseName: 'Release v2.0.0',
      releaseNotes: '### Added\n- Something new.',
    });
    renderFooter();

    expect(await screen.findByText(/v2\.0\.0/)).toBeInTheDocument();
    const releaseLink = screen.getByRole('link', { name: 'View on GitHub' });
    expect(releaseLink).toHaveAttribute(
      'href',
      'https://github.com/myastroboard/myastroshine/releases/tag/v2.0.0',
    );
  });

  it('opens the release notes in a modal from "What\'s new"', async () => {
    mocked.checkForUpdates.mockResolvedValue({
      ...BASE_RESULT,
      latestVersion: '2.0.0',
      updateAvailable: true,
      releaseUrl: 'https://github.com/myastroboard/myastroshine/releases/tag/v2.0.0',
      releaseName: 'Release v2.0.0',
      releaseNotes: '### Added\n- Something new.',
    });
    renderFooter();

    await screen.findByText(/v2\.0\.0/);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: "What's new" }));

    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Added' })).toBeInTheDocument();
    expect(screen.getByText('Something new.')).toBeInTheDocument();

    // Regression: the footer has `backdrop-blur` (a `backdrop-filter`), which
    // creates a containing block for `position: fixed` descendants - without
    // a portal, the modal would render trapped inside the footer's box
    // instead of covering the viewport.
    expect(dialog.closest('footer')).toBeNull();
  });

  it('falls back to the dev version when VITE_APP_VERSION is unset', async () => {
    const env = import.meta.env as unknown as Record<string, string | undefined>;
    const original = env.VITE_APP_VERSION;
    delete env.VITE_APP_VERSION;
    mocked.checkForUpdates.mockResolvedValue({ ...BASE_RESULT });
    try {
      renderFooter();
      expect(screen.getByText(/v0\.0\.0-dev/)).toBeInTheDocument();
    } finally {
      env.VITE_APP_VERSION = original;
    }
    await waitFor(() => expect(mocked.checkForUpdates).toHaveBeenCalled());
  });

  it('uses the configured app name and version when set', async () => {
    vi.stubEnv('VITE_APP_NAME', 'ShineTest');
    vi.stubEnv('VITE_APP_VERSION', '9.9.9');
    mocked.checkForUpdates.mockResolvedValue({ ...BASE_RESULT });
    renderFooter();

    expect(screen.getByText('ShineTest · v9.9.9')).toBeInTheDocument();
    await waitFor(() => expect(mocked.checkForUpdates).toHaveBeenCalled());
  });

  it('shows the update line without a GitHub link or "What\'s new" when the release carries neither', async () => {
    mocked.checkForUpdates.mockResolvedValue({
      ...BASE_RESULT,
      latestVersion: '2.0.0',
      updateAvailable: true,
      releaseUrl: null,
      releaseName: null,
      releaseNotes: null,
    });
    renderFooter();

    expect(await screen.findByText(/v2\.0\.0/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'View on GitHub' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: "What's new" })).not.toBeInTheDocument();
  });

  it('falls back to the version number as the modal release name when unset', async () => {
    mocked.checkForUpdates.mockResolvedValue({
      ...BASE_RESULT,
      latestVersion: '2.0.0',
      updateAvailable: true,
      releaseUrl: 'https://github.com/myastroboard/myastroshine/releases/tag/v2.0.0',
      releaseName: null,
      releaseNotes: '### Added\n- Something new.',
    });
    renderFooter();

    await screen.findByText(/v2\.0\.0/);
    fireEvent.click(screen.getByRole('button', { name: "What's new" }));

    expect(screen.getByRole('heading', { name: '2.0.0' })).toBeInTheDocument();
  });

  it('closes the release notes modal', async () => {
    mocked.checkForUpdates.mockResolvedValue({
      ...BASE_RESULT,
      latestVersion: '2.0.0',
      updateAvailable: true,
      releaseUrl: 'https://github.com/myastroboard/myastroshine/releases/tag/v2.0.0',
      releaseName: 'Release v2.0.0',
      releaseNotes: '### Added\n- Something new.',
    });
    renderFooter();

    await screen.findByText(/v2\.0\.0/);
    fireEvent.click(screen.getByRole('button', { name: "What's new" }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
