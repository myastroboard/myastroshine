import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Footer } from '@/components/Footer';
import { apiClient } from '@/services/api';
import type { VersionCheckResult } from '@/types';

vi.mock('@/services/api', () => ({
  apiClient: { checkForUpdates: vi.fn() },
}));

const mocked = vi.mocked(apiClient);

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

  it('always shows the app name and a GitHub link', async () => {
    mocked.checkForUpdates.mockResolvedValue({ ...BASE_RESULT });
    render(<Footer />);

    expect(screen.getByText(/MyAstroShine/)).toBeInTheDocument();
    const link = screen.getByRole('link', { name: 'GitHub' });
    expect(link).toHaveAttribute('href', 'https://github.com/myastroboard/myastroshine');
    await waitFor(() => expect(mocked.checkForUpdates).toHaveBeenCalled());
  });

  it('has no update notice when no update is available', async () => {
    mocked.checkForUpdates.mockResolvedValue({ ...BASE_RESULT });
    render(<Footer />);

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
    render(<Footer />);

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
    render(<Footer />);

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
});
