import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { UpdateBanner } from '@/components/UpdateBanner';
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

describe('UpdateBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when no update is available', async () => {
    mocked.checkForUpdates.mockResolvedValue({ ...BASE_RESULT });
    render(<UpdateBanner />);

    await waitFor(() => expect(mocked.checkForUpdates).toHaveBeenCalled());
    expect(screen.queryByText(/new version/i)).not.toBeInTheDocument();
  });

  it('shows the banner with a link and release notes once expanded', async () => {
    mocked.checkForUpdates.mockResolvedValue({
      ...BASE_RESULT,
      latestVersion: '2.0.0',
      updateAvailable: true,
      releaseUrl: 'https://github.com/myastroboard/myastroshine/releases/tag/v2.0.0',
      releaseName: 'Release v2.0.0',
      releaseNotes: '### Added\n- Something new.',
    });
    render(<UpdateBanner />);

    expect(await screen.findByText(/v2\.0\.0/)).toBeInTheDocument();
    const link = screen.getByRole('link', { name: 'View on GitHub' });
    expect(link).toHaveAttribute(
      'href',
      'https://github.com/myastroboard/myastroshine/releases/tag/v2.0.0',
    );

    expect(screen.getByText(/Something new/)).not.toBeVisible();
    fireEvent.click(screen.getByText("What's new"));
    expect(screen.getByText(/Something new/)).toBeVisible();
  });

  it('does not show the banner if the server result is not actually newer', async () => {
    mocked.checkForUpdates.mockResolvedValue({
      ...BASE_RESULT,
      currentVersion: '1.2.0',
      latestVersion: '1.2.0',
      updateAvailable: true, // a stale/incorrect server result
    });
    render(<UpdateBanner />);

    await waitFor(() => expect(mocked.checkForUpdates).toHaveBeenCalled());
    expect(screen.queryByText(/new version/i)).not.toBeInTheDocument();
  });
});
