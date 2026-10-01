import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SettingsView } from '@/components/SettingsView';
import { ApiError, apiClient } from '@/services/api';
import type { AppSettings } from '@/types';

vi.mock('@/services/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/api')>()),
  apiClient: {
    getAuthStatus: vi.fn(),
    setupAdmin: vi.fn(),
    loginAdmin: vi.fn(),
    logoutAdmin: vi.fn(),
    changeAdminPassword: vi.fn(),
    listAdminSessions: vi.fn(),
    revokeAdminSession: vi.fn(),
    getAppSettings: vi.fn(),
    saveAppSettings: vi.fn(),
    getEngineStatus: vi.fn(),
    stageEngine: vi.fn(),
    installEngine: vi.fn(),
    discardStagedEngine: vi.fn(),
    removeEngine: vi.fn(),
    listTokens: vi.fn(),
    createToken: vi.fn(),
    revokeToken: vi.fn(),
    getLogs: vi.fn(),
    getLogLevels: vi.fn(),
    clearLogs: vi.fn(),
    exportLogs: vi.fn(),
    getJobs: vi.fn(),
    getDiskUsage: vi.fn(),
    exportConfig: vi.fn(),
    importConfig: vi.fn(),
  },
}));

const mocked = vi.mocked(apiClient);

const SETTINGS: AppSettings = {
  adminSessionIdleDays: 7,
  corsOrigins: ['http://localhost:3000'],
  rateLimitEnabled: true,
  rateLimitPerMinute: 10,
  maxConcurrentJobsPerIp: 5,
  maxImageSizeMb: 100,
  sessionExpiryHours: 24,
  previewMaxSize: 512,
  astrodexCallbackUrls: [],
  astrodexMaxRetries: 3,
  astrodexRetryDelaySeconds: 5,
  stackingEnabled: true,
  stackingMaxFrames: 2000,
  stackingRetentionHours: 12,
  stackingWorkers: 0,
  stackingWatchDir: '',
  stackingWatchIdleMinutes: 10,
  stackingWatchAutoProcess: true,
  starnet2Path: '',
  deepsnrPath: '',
  starnet2Stride: 0,
  deepsnrStride: 0,
  logLevel: 'info',
  consoleLogLevel: 'warning',
  jobHistoryRetentionHours: 168,
};

function renderView() {
  return render(<SettingsView onClose={vi.fn()} />);
}

describe('SettingsView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.getAuthStatus.mockResolvedValue({ adminEnabled: true, configured: true, authenticated: true });
    mocked.listAdminSessions.mockResolvedValue([]);
    mocked.getAppSettings.mockResolvedValue({ ...SETTINGS });
    mocked.saveAppSettings.mockImplementation((next) => Promise.resolve(next));
    mocked.getEngineStatus.mockResolvedValue({
      starnet2: { configured: false, found: false, version: null, knownGood: false, detail: 'x' },
      deepsnr: { configured: false, found: false, version: null, knownGood: false, detail: 'x' },
    });
    mocked.listTokens.mockResolvedValue({ tokens: [], total: 0 });
    mocked.getLogs.mockResolvedValue({
      lines: ['2026-09-04 10:00:00,000 +0000 - app.main - INFO [x:1] - started'],
      returned: 1,
      filteredLevel: null,
    });
    mocked.getLogLevels.mockResolvedValue({ file: 'info', console: 'warning' });
    mocked.getJobs.mockResolvedValue({ jobs: [], total: 0, limit: 25, offset: 0 });
    mocked.getDiskUsage.mockResolvedValue({
      totalBytes: 100_000_000_000,
      usedBytes: 40_000_000_000,
      freeBytes: 60_000_000_000,
      imagesBytes: 1_000_000,
      stacksBytes: 2_000_000,
      dbBytes: 500_000,
      logsBytes: 100_000,
    });
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
      expect.objectContaining({ maxImageSizeMb: 250, stackingMaxFrames: 2000 }),
    );
  });

  it('shows the token manager under the AstroDex section', async () => {
    renderView();
    await screen.findByLabelText('Maximum upload size');

    fireEvent.click(screen.getByRole('button', { name: 'AstroDex' }));

    expect(screen.getByText(/webhook tokens/i)).toBeInTheDocument();
  });

  it('toggles a boolean setting via the switch', async () => {
    renderView();
    await screen.findByLabelText('Maximum upload size');
    fireEvent.click(screen.getByRole('button', { name: 'Stacking' }));

    const toggle = screen.getByRole('switch', { name: 'Stacking enabled' });
    expect(toggle).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-checked', 'false');
  });

  it('edits rate limiting settings under the Security section', async () => {
    renderView();
    await screen.findByLabelText('Maximum upload size');

    fireEvent.click(screen.getByRole('button', { name: 'Security' }));

    const perMinute = await screen.findByLabelText('Requests per minute');
    expect(perMinute).toHaveValue(10);
    fireEvent.change(perMinute, { target: { value: '20' } });
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(mocked.saveAppSettings).toHaveBeenCalledTimes(1));
    expect(mocked.saveAppSettings).toHaveBeenCalledWith(
      expect.objectContaining({ rateLimitPerMinute: 20 }),
    );
  });

  it('tails the log file under the Logs section', async () => {
    renderView();
    await screen.findByLabelText('Maximum upload size');

    fireEvent.click(screen.getByRole('button', { name: 'Logs' }));

    await waitFor(() => expect(screen.getByText(/INFO \[x:1\] - started/)).toBeInTheDocument());
    expect(mocked.getLogs).toHaveBeenCalled();
  });

  it('shows disk usage and job history under the Maintenance section', async () => {
    mocked.getJobs.mockResolvedValue({
      jobs: [
        {
          jobId: 'job-1',
          sessionId: 'sess-1',
          status: 'failed',
          progressPercent: 40,
          currentStep: 'denoise',
          error: 'boom',
          createdAt: '2026-09-11T10:00:00Z',
          updatedAt: '2026-09-11T10:00:01Z',
        },
      ],
      total: 1,
      limit: 25,
      offset: 0,
    });
    renderView();
    await screen.findByLabelText('Maximum upload size');

    fireEvent.click(screen.getByRole('button', { name: 'Maintenance' }));

    expect(await screen.findByText('boom')).toBeInTheDocument();
    expect(screen.getByText(/37.3 GB \/ 93.1 GB/)).toBeInTheDocument();
    expect(mocked.getJobs).toHaveBeenCalled();
    expect(mocked.getDiskUsage).toHaveBeenCalled();
  });

  it('filters job history by status', async () => {
    renderView();
    await screen.findByLabelText('Maximum upload size');
    fireEvent.click(screen.getByRole('button', { name: 'Maintenance' }));
    await waitFor(() => expect(mocked.getJobs).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'failed' } });

    await waitFor(() =>
      expect(mocked.getJobs).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: 'failed' }),
      ),
    );
  });

  it('imports a config file under the Maintenance section and reports the result', async () => {
    mocked.importConfig.mockResolvedValue({ presetsImported: 2, presetsSkipped: ['Mine'] });
    renderView();
    await screen.findByLabelText('Maximum upload size');
    fireEvent.click(screen.getByRole('button', { name: 'Maintenance' }));
    await screen.findByRole('button', { name: 'Import configuration' });

    const file = new File(
      [JSON.stringify({ formatVersion: 1, settings: SETTINGS, presets: [] })],
      'config.json',
      { type: 'application/json' },
    );
    const input = document.querySelector('input[type="file"][accept="application/json"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByText(/2 preset\(s\) imported, 1 skipped/)).toBeInTheDocument();
    expect(mocked.importConfig).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(mocked.getAppSettings).toHaveBeenCalledTimes(2)); // initial load + refresh
  });

  it('exports the config as a downloadable file under the Maintenance section', async () => {
    mocked.exportConfig.mockResolvedValue({
      formatVersion: 1,
      appVersion: '0.4.1',
      exportedAt: '2026-09-11T00:00:00Z',
      settings: SETTINGS,
      presets: [],
    });
    renderView();
    await screen.findByLabelText('Maximum upload size');
    fireEvent.click(screen.getByRole('button', { name: 'Maintenance' }));

    fireEvent.click(screen.getByRole('button', { name: 'Export configuration' }));

    await waitFor(() => expect(mocked.exportConfig).toHaveBeenCalledTimes(1));
  });

  it('probes the external engine paths under the ML engines section', async () => {
    mocked.getEngineStatus.mockResolvedValue({
      starnet2: {
        configured: true,
        found: true,
        version: '2.6.1',
        knownGood: true,
        detail: 'StarNet2 2.6.1 detected',
      },
      deepsnr: { configured: false, found: false, version: null, knownGood: false, detail: 'x' },
    });
    renderView();
    await screen.findByLabelText('Maximum upload size');

    fireEvent.click(screen.getByRole('button', { name: 'ML engines' }));

    const path = await screen.findByLabelText('StarNet2 binary path');
    fireEvent.change(path, { target: { value: '/opt/engines/starnet2/starnet2' } });
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(mocked.saveAppSettings).toHaveBeenCalledTimes(1));
    expect(mocked.saveAppSettings).toHaveBeenCalledWith(
      expect.objectContaining({ starnet2Path: '/opt/engines/starnet2/starnet2' }),
    );
    expect(await screen.findByText('StarNet2 2.6.1 detected')).toBeInTheDocument();
    expect(mocked.getEngineStatus).toHaveBeenCalled();
  });

  describe('admin gate', () => {
    it('shows the setup form on first run and never loads the settings', async () => {
      mocked.getAuthStatus.mockResolvedValue({ adminEnabled: true, configured: false, authenticated: false });
      renderView();

      expect(await screen.findByText('Create the admin password')).toBeInTheDocument();
      expect(mocked.getAppSettings).not.toHaveBeenCalled();
    });

    it('sets the password up and then shows the settings', async () => {
      mocked.getAuthStatus.mockResolvedValueOnce({ adminEnabled: true, configured: false, authenticated: false });
      mocked.setupAdmin.mockResolvedValue(undefined);
      renderView();
      await screen.findByText('Create the admin password');

      fireEvent.change(screen.getByLabelText(/^new password$/i), { target: { value: 'a long password' } });
      fireEvent.change(screen.getByLabelText(/confirm the password/i), { target: { value: 'a long password' } });
      fireEvent.click(screen.getByRole('button', { name: /create and log in/i }));

      await waitFor(() => expect(mocked.getAppSettings).toHaveBeenCalled());
      expect(mocked.setupAdmin).toHaveBeenCalledWith('a long password');
    });

    it('asks for the password when not logged in', async () => {
      mocked.getAuthStatus.mockResolvedValue({ adminEnabled: true, configured: true, authenticated: false });
      renderView();

      expect(await screen.findByText('Administrator login')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^log out$/i })).not.toBeInTheDocument();
    });

    it('says so when the admin API is turned off', async () => {
      mocked.getAuthStatus.mockResolvedValue({ adminEnabled: false, configured: false, authenticated: false });
      renderView();

      expect(await screen.findByText(/ADMIN_ENABLED=false/)).toBeInTheDocument();
    });

    it('reports a failure to reach the auth status', async () => {
      mocked.getAuthStatus.mockRejectedValue(new ApiError(503, 'down'));
      renderView();

      expect(await screen.findByRole('alert')).toBeInTheDocument();
    });

    it('logs out from the header', async () => {
      mocked.logoutAdmin.mockResolvedValue(undefined);
      renderView();
      const logout = await screen.findByRole('button', { name: /^log out$/i });
      mocked.getAuthStatus.mockResolvedValue({ adminEnabled: true, configured: true, authenticated: false });

      fireEvent.click(logout);

      expect(await screen.findByText('Administrator login')).toBeInTheDocument();
      expect(mocked.logoutAdmin).toHaveBeenCalled();
    });

    it('shows the Security section with the session lifetime and the password form', async () => {
      renderView();
      fireEvent.click(await screen.findByRole('button', { name: 'Security' }));

      expect(await screen.findByLabelText(/stay logged in/i)).toHaveValue(7);
      expect(screen.getByText('Change the admin password')).toBeInTheDocument();
      fireEvent.change(screen.getByLabelText(/stay logged in/i), { target: { value: '3' } });
      expect(screen.getByText(/unsaved changes/i)).toBeInTheDocument();
    });

    it('returns to the login form when this browser is logged out from the Security list', async () => {
      mocked.listAdminSessions.mockResolvedValue([
        {
          id: 'mine',
          clientIp: '10.0.0.2',
          userAgent: 'Firefox',
          createdAt: '2026-09-30T10:00:00Z',
          lastSeenAt: '2026-09-30T11:00:00Z',
          current: true,
        },
      ]);
      mocked.revokeAdminSession.mockResolvedValue(undefined);
      renderView();
      fireEvent.click(await screen.findByRole('button', { name: 'Security' }));
      await screen.findByText('Firefox');
      mocked.getAuthStatus.mockResolvedValue({ adminEnabled: true, configured: true, authenticated: false });

      const buttons = screen.getAllByRole('button', { name: /^log out$/i });
      fireEvent.click(buttons[buttons.length - 1]);

      expect(await screen.findByText('Administrator login')).toBeInTheDocument();
    });
  });

  describe('every field reaches the saved settings', () => {
    /** Edit every control in the visible section: numbers, text, lists, selects, switches. */
    function editEverything(section: string): void {
      const panel = screen
        .getByRole('heading', { level: 2, name: section })
        .closest('.panel') as HTMLElement;
      panel.querySelectorAll<HTMLInputElement>('input[type="number"]').forEach((input) => {
        fireEvent.change(input, { target: { value: '42' } });
      });
      panel.querySelectorAll<HTMLInputElement>('input[type="text"]').forEach((input) => {
        fireEvent.change(input, { target: { value: '/edited' } });
      });
      panel.querySelectorAll('textarea').forEach((area) => {
        fireEvent.change(area, { target: { value: 'http://a.example\nhttp://b.example' } });
      });
      panel.querySelectorAll('select').forEach((select) => {
        fireEvent.change(select, { target: { value: 'critical' } });
      });
      panel.querySelectorAll<HTMLButtonElement>('[role="switch"]').forEach((toggle) => {
        fireEvent.click(toggle);
      });
    }

    async function saveAndRead(): Promise<AppSettings> {
      fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
      await waitFor(() => expect(mocked.saveAppSettings).toHaveBeenCalled());
      return mocked.saveAppSettings.mock.calls.at(-1)?.[0] as AppSettings;
    }

    it('General', async () => {
      renderView();
      await screen.findByLabelText('Maximum upload size');

      editEverything('General');
      const saved = await saveAndRead();

      expect(saved).toMatchObject({ maxImageSizeMb: 42, sessionExpiryHours: 42, previewMaxSize: 42 });
    });

    it('Stacking', async () => {
      renderView();
      await screen.findByLabelText('Maximum upload size');
      fireEvent.click(screen.getByRole('button', { name: 'Stacking' }));

      editEverything('Stacking');
      const saved = await saveAndRead();

      expect(saved).toMatchObject({
        stackingEnabled: false,
        stackingMaxFrames: 42,
        stackingRetentionHours: 42,
        stackingWorkers: 42,
        stackingWatchDir: '/edited',
        stackingWatchIdleMinutes: 42,
        stackingWatchAutoProcess: false,
      });
    });

    it('ML engines', async () => {
      renderView();
      await screen.findByLabelText('Maximum upload size');
      fireEvent.click(screen.getByRole('button', { name: 'ML engines' }));
      await screen.findByLabelText('StarNet2 binary path');

      editEverything('ML engines');
      const saved = await saveAndRead();

      expect(saved).toMatchObject({
        starnet2Path: '/edited',
        deepsnrPath: '/edited',
        starnet2Stride: 42,
        deepsnrStride: 42,
      });
    });

    it('AstroDex', async () => {
      renderView();
      await screen.findByLabelText('Maximum upload size');
      fireEvent.click(screen.getByRole('button', { name: 'AstroDex' }));
      await waitFor(() => expect(document.querySelector('textarea')).not.toBeNull());

      editEverything('AstroDex');
      const saved = await saveAndRead();

      expect(saved).toMatchObject({
        astrodexCallbackUrls: ['http://a.example', 'http://b.example'],
        astrodexMaxRetries: 42,
        astrodexRetryDelaySeconds: 42,
      });
    });

    it('Security', async () => {
      renderView();
      await screen.findByLabelText('Maximum upload size');
      fireEvent.click(screen.getByRole('button', { name: 'Security' }));
      await screen.findByLabelText(/stay logged in/i);

      editEverything('Security');
      const saved = await saveAndRead();

      expect(saved).toMatchObject({
        adminSessionIdleDays: 42,
        corsOrigins: ['http://a.example', 'http://b.example'],
        rateLimitEnabled: false,
        rateLimitPerMinute: 42,
        maxConcurrentJobsPerIp: 42,
      });
    });

    it('Logs and Maintenance', async () => {
      renderView();
      await screen.findByLabelText('Maximum upload size');
      fireEvent.click(screen.getByRole('button', { name: 'Logs' }));
      fireEvent.change(await screen.findByLabelText('File log level'), {
        target: { value: 'critical' },
      });
      fireEvent.change(screen.getByLabelText('Console log level'), {
        target: { value: 'error' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Maintenance' }));
      await waitFor(() => expect(mocked.getJobs).toHaveBeenCalled());
      fireEvent.change(screen.getByLabelText('Job history retention'), { target: { value: '42' } });

      const saved = await saveAndRead();

      expect(saved).toMatchObject({
        logLevel: 'critical',
        consoleLogLevel: 'error',
        jobHistoryRetentionHours: 42,
      });
    });
  });

  describe('failure and edge states', () => {
    it('shows a failure to load the settings', async () => {
      mocked.getAppSettings.mockRejectedValue(new Error('Admin login required'));
      renderView();

      expect(await screen.findByText('Admin login required')).toBeInTheDocument();
    });

    it('shows a loading line until the settings arrive', async () => {
      mocked.getAppSettings.mockReturnValue(new Promise(() => undefined));
      renderView();

      // The panels mount once the admin gate opens; until the settings land
      // they show a loading line.
      await screen.findByRole('button', { name: 'AstroDex' });
      expect(await screen.findByText('Loading...')).toBeInTheDocument();
    });

    it('reports a failed export and a failed import, and ignores an empty pick', async () => {
      mocked.exportConfig.mockRejectedValue(new Error('Export blew up'));
      mocked.importConfig.mockRejectedValue('not an Error');
      renderView();
      await screen.findByLabelText('Maximum upload size');
      fireEvent.click(screen.getByRole('button', { name: 'Maintenance' }));

      fireEvent.click(await screen.findByRole('button', { name: 'Export configuration' }));
      expect(await screen.findByText('Export blew up')).toBeInTheDocument();

      const input = document.querySelector('input[type="file"][accept="application/json"]') as HTMLInputElement;
      fireEvent.change(input, { target: { files: [] } });
      expect(mocked.importConfig).not.toHaveBeenCalled();

      const file = new File([JSON.stringify({ formatVersion: 1 })], 'config.json');
      fireEvent.change(input, { target: { files: [file] } });
      expect(await screen.findByText('Import failed')).toBeInTheDocument();
    });

    it('colours an engine status by what the probe found', async () => {
      mocked.getEngineStatus.mockResolvedValue({
        starnet2: {
          configured: true,
          found: true,
          version: '3.0.0',
          knownGood: false,
          detail: 'untested 3.0.0',
        },
        deepsnr: {
          configured: true,
          found: false,
          version: null,
          knownGood: false,
          detail: 'Not found at /x',
        },
      });
      renderView();
      await screen.findByLabelText('Maximum upload size');
      fireEvent.click(screen.getByRole('button', { name: 'ML engines' }));

      expect(await screen.findByText('untested 3.0.0')).toHaveClass('text-warning');
      expect(screen.getByText('Not found at /x')).toHaveClass('text-danger');
    });

    it('filters, refreshes, exports and clears the log after a confirmation', async () => {
      mocked.clearLogs.mockResolvedValue(undefined);
      mocked.exportLogs.mockResolvedValue(new Blob(['zip']));
      renderView();
      await screen.findByLabelText('Maximum upload size');
      fireEvent.click(screen.getByRole('button', { name: 'Logs' }));
      await screen.findByText(/started/);

      fireEvent.change(screen.getByLabelText('Level'), { target: { value: 'error' } });
      await waitFor(() => expect(mocked.getLogs).toHaveBeenLastCalledWith(300, 'error'));
      fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
      fireEvent.click(screen.getByRole('button', { name: 'Export ZIP' }));
      await waitFor(() => expect(mocked.exportLogs).toHaveBeenCalled());

      fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
      expect(mocked.clearLogs).not.toHaveBeenCalled();
      fireEvent.blur(screen.getByRole('button', { name: 'Confirm clear' }));
      fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
      fireEvent.click(screen.getByRole('button', { name: 'Confirm clear' }));
      await waitFor(() => expect(mocked.clearLogs).toHaveBeenCalledTimes(1));
    });

    it('shows a failure to read the log', async () => {
      mocked.getLogs.mockRejectedValue(new Error('Log unreadable'));
      renderView();
      await screen.findByLabelText('Maximum upload size');
      fireEvent.click(screen.getByRole('button', { name: 'Logs' }));

      expect(await screen.findByText('Log unreadable')).toBeInTheDocument();
    });

    it('pages through a long job history and shows jobs without a session or error', async () => {
      mocked.getJobs.mockResolvedValue({
        jobs: [
          {
            jobId: 'job-2',
            sessionId: null,
            status: 'completed',
            progressPercent: 100,
            currentStep: 'done',
            error: null,
            createdAt: '2026-09-11T10:00:00Z',
            updatedAt: '2026-09-11T10:00:01Z',
          },
        ],
        total: 60,
        limit: 25,
        offset: 0,
      });
      renderView();
      await screen.findByLabelText('Maximum upload size');
      fireEvent.click(screen.getByRole('button', { name: 'Maintenance' }));

      expect(await screen.findByText('1-25 of 60')).toBeInTheDocument();
      expect(screen.getByText('-')).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: 'Next' }));
      await waitFor(() =>
        expect(mocked.getJobs).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 25 })),
      );
      fireEvent.click(await screen.findByRole('button', { name: 'Previous' }));
      await waitFor(() =>
        expect(mocked.getJobs).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 0 })),
      );
    });

    it('shows a failure to load the job history', async () => {
      mocked.getJobs.mockRejectedValue(new Error('Jobs unavailable'));
      renderView();
      await screen.findByLabelText('Maximum upload size');
      fireEvent.click(screen.getByRole('button', { name: 'Maintenance' }));

      expect(await screen.findByText('Jobs unavailable')).toBeInTheDocument();
    });

    it('opens the import picker and re-checks the engines, tolerating a probe failure', async () => {
      renderView();
      await screen.findByLabelText('Maximum upload size');
      fireEvent.click(screen.getByRole('button', { name: 'Maintenance' }));
      const click = vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(() => undefined);

      fireEvent.click(await screen.findByRole('button', { name: 'Import configuration' }));
      expect(click).toHaveBeenCalled();
      click.mockRestore();

      fireEvent.click(screen.getByRole('button', { name: 'ML engines' }));
      await waitFor(() => expect(mocked.getEngineStatus).toHaveBeenCalledTimes(1));
      mocked.getEngineStatus.mockRejectedValueOnce(new Error('probe failed'));
      fireEvent.click(screen.getByRole('button', { name: /re-check engines/i }));
      await waitFor(() => expect(mocked.getEngineStatus).toHaveBeenCalledTimes(2));
      expect(screen.getByRole('button', { name: /re-check engines/i })).toBeEnabled();
    });

    it('shows a generic message when an export fails with a non-Error value', async () => {
      mocked.exportConfig.mockRejectedValue('offline');
      renderView();
      await screen.findByLabelText('Maximum upload size');
      fireEvent.click(screen.getByRole('button', { name: 'Maintenance' }));

      fireEvent.click(await screen.findByRole('button', { name: 'Export configuration' }));

      expect(await screen.findByText('Export failed')).toBeInTheDocument();
    });

    it('shows the server message when an import fails with an Error', async () => {
      mocked.importConfig.mockRejectedValue(new Error('Unsupported format version'));
      renderView();
      await screen.findByLabelText('Maximum upload size');
      fireEvent.click(screen.getByRole('button', { name: 'Maintenance' }));
      await screen.findByRole('button', { name: 'Import configuration' });

      const input = document.querySelector('input[type="file"][accept="application/json"]') as HTMLInputElement;
      fireEvent.change(input, { target: { files: [new File(['{}'], 'config.json')] } });

      expect(await screen.findByText('Unsupported format version')).toBeInTheDocument();
    });

    it('installs an engine from its archive and shows its new path', async () => {
      mocked.stageEngine.mockResolvedValue({
        stagingId: 'abc',
        engine: 'starnet2',
        archiveName: 'starnet2.zip',
        status: { configured: true, found: true, version: '2.6.1', knownGood: true, detail: 'ok' },
        licenseText: 'LICENSE',
      });
      mocked.installEngine.mockResolvedValue({
        configured: true,
        found: true,
        version: '2.6.1',
        knownGood: true,
        detail: 'ok',
        installed: {
          version: '2.6.1',
          archiveName: 'starnet2.zip',
          licenseAcceptedAt: '2026-10-01T07:00:00Z',
          path: '/data/engines/starnet2/starnet2',
        },
      });
      renderView();
      await screen.findByLabelText('Maximum upload size');
      fireEvent.click(screen.getByRole('button', { name: 'ML engines' }));
      await screen.findByLabelText('StarNet2 binary path');

      fireEvent.change(screen.getByLabelText('StarNet2 archive'), {
        target: { files: [new File(['z'], 'starnet2.zip')] },
      });
      fireEvent.click(await screen.findByRole('checkbox', { name: /accept its licence/i }));
      fireEvent.click(screen.getByRole('button', { name: 'Install' }));

      await waitFor(() =>
        expect(screen.getByLabelText('StarNet2 binary path')).toHaveValue(
          '/data/engines/starnet2/starnet2',
        ),
      );
      expect(screen.queryByText(/unsaved changes/i)).not.toBeInTheDocument();
      expect(mocked.getEngineStatus).toHaveBeenCalledTimes(2); // re-checked after the install
    });

    it('clears the DeepSNR path once its uploaded package is removed', async () => {
      mocked.getAppSettings.mockResolvedValue({ ...SETTINGS, deepsnrPath: '/data/engines/deepsnr/deepsnr' });
      mocked.getEngineStatus.mockResolvedValue({
        starnet2: { configured: false, found: false, version: null, knownGood: false, detail: 'x' },
        deepsnr: {
          configured: true,
          found: true,
          version: '1.3.1',
          knownGood: true,
          detail: 'DeepSNR 1.3.1 detected',
          installed: {
            version: '1.3.1',
            archiveName: 'deepsnr.zip',
            licenseAcceptedAt: '2026-10-01T07:00:00Z',
            path: '/data/engines/deepsnr/deepsnr',
          },
        },
      });
      mocked.removeEngine.mockResolvedValue(undefined);
      renderView();
      await screen.findByLabelText('Maximum upload size');
      fireEvent.click(screen.getByRole('button', { name: 'ML engines' }));

      fireEvent.click(await screen.findByRole('button', { name: 'Remove' }));
      fireEvent.click(screen.getByRole('button', { name: 'Confirm removal' }));

      await waitFor(() => expect(screen.getByLabelText('DeepSNR binary path')).toHaveValue(''));
    });
  });
});
