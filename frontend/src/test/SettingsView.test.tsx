import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SettingsView } from '@/components/SettingsView';
import { apiClient } from '@/services/api';
import type { AppSettings } from '@/types';

vi.mock('@/services/api', () => ({
  apiClient: {
    getAppSettings: vi.fn(),
    saveAppSettings: vi.fn(),
    listTokens: vi.fn(),
    createToken: vi.fn(),
    revokeToken: vi.fn(),
    getLogs: vi.fn(),
    getLogLevels: vi.fn(),
    clearLogs: vi.fn(),
    exportLogs: vi.fn(),
  },
}));

const mocked = vi.mocked(apiClient);

const SETTINGS: AppSettings = {
  corsOrigins: ['http://localhost:3000'],
  maxImageSizeMb: 100,
  sessionExpiryHours: 24,
  previewMaxSize: 512,
  astrodexCallbackUrls: [],
  astrodexMaxRetries: 3,
  astrodexRetryDelaySeconds: 5,
  denoiseEnableMl: false,
  depthDetectionMethod: 'gradient',
  stackingEnabled: true,
  stackingMaxFrames: 100,
  stackingDetector: 'orb',
  stackingCombinationDefault: 'median',
  stackingCosmicRayThreshold: 3,
  logLevel: 'info',
  consoleLogLevel: 'warning',
};

function renderView() {
  return render(<SettingsView onClose={vi.fn()} />);
}

describe('SettingsView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.getAppSettings.mockResolvedValue({ ...SETTINGS });
    mocked.saveAppSettings.mockImplementation((next) => Promise.resolve(next));
    mocked.listTokens.mockResolvedValue({ tokens: [], total: 0 });
    mocked.getLogs.mockResolvedValue({
      lines: ['2026-09-04 10:00:00,000 +0000 - app.main - INFO [x:1] - started'],
      returned: 1,
      filteredLevel: null,
    });
    mocked.getLogLevels.mockResolvedValue({ file: 'info', console: 'warning' });
  });

  it('loads current values and only shows Save once something changed', async () => {
    renderView();

    const maxSize = await screen.findByLabelText('Maximum upload size');
    expect(maxSize).toHaveValue(100);
    expect(screen.queryByRole('button', { name: /save changes/i })).not.toBeInTheDocument();

    fireEvent.change(maxSize, { target: { value: '250' } });

    expect(screen.getByRole('button', { name: /save changes/i })).toBeInTheDocument();
  });

  it('posts the whole edited object back', async () => {
    renderView();

    const maxSize = await screen.findByLabelText('Maximum upload size');
    fireEvent.change(maxSize, { target: { value: '250' } });
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(mocked.saveAppSettings).toHaveBeenCalledTimes(1));
    expect(mocked.saveAppSettings).toHaveBeenCalledWith(
      expect.objectContaining({ maxImageSizeMb: 250, stackingDetector: 'orb' }),
    );
  });

  it('shows the token manager under the Webhooks section', async () => {
    renderView();
    await screen.findByLabelText('Maximum upload size');

    fireEvent.click(screen.getByRole('button', { name: 'Webhooks' }));

    expect(screen.getByText(/webhook tokens/i)).toBeInTheDocument();
  });

  it('toggles a boolean setting via the switch', async () => {
    renderView();
    await screen.findByLabelText('Maximum upload size');

    const toggle = screen.getByRole('switch', { name: 'ML denoising' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-checked', 'true');
  });

  it('tails the log file under the Logs section', async () => {
    renderView();
    await screen.findByLabelText('Maximum upload size');

    fireEvent.click(screen.getByRole('button', { name: 'Logs' }));

    await waitFor(() => expect(screen.getByText(/INFO \[x:1\] - started/)).toBeInTheDocument());
    expect(mocked.getLogs).toHaveBeenCalled();
  });
});
