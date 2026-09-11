import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAppSettings } from '@/hooks/useAppSettings';
import { apiClient } from '@/services/api';
import type { AppSettings } from '@/types';

vi.mock('@/services/api', () => ({
  apiClient: { getAppSettings: vi.fn(), saveAppSettings: vi.fn() },
}));

const mocked = vi.mocked(apiClient);

const SETTINGS: AppSettings = {
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

describe('useAppSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads settings on mount', async () => {
    mocked.getAppSettings.mockResolvedValue({ ...SETTINGS });
    const { result } = renderHook(() => useAppSettings());

    expect(result.current.isLoading).toBe(true);

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.draft).toEqual(SETTINGS);
    expect(result.current.dirty).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('sets an error message when loading fails with an Error', async () => {
    mocked.getAppSettings.mockRejectedValue(new Error('network down'));
    const { result } = renderHook(() => useAppSettings());

    await waitFor(() => expect(result.current.error).toBe('network down'));
    expect(result.current.isLoading).toBe(false);
    expect(result.current.draft).toBeNull();
  });

  it('falls back to a generic message when loading fails with a non-Error', async () => {
    mocked.getAppSettings.mockRejectedValue('oops');
    const { result } = renderHook(() => useAppSettings());

    await waitFor(() => expect(result.current.error).toBe('Failed to load settings'));
  });

  it('patch merges changes into the draft', async () => {
    mocked.getAppSettings.mockResolvedValue({ ...SETTINGS });
    const { result } = renderHook(() => useAppSettings());
    await waitFor(() => expect(result.current.draft).toEqual(SETTINGS));

    act(() => result.current.patch({ maxImageSizeMb: 250 }));

    expect(result.current.draft?.maxImageSizeMb).toBe(250);
    expect(result.current.dirty).toBe(true);
  });

  it('patch is a no-op before the draft has loaded', () => {
    mocked.getAppSettings.mockReturnValue(new Promise<AppSettings>(() => {}));
    const { result } = renderHook(() => useAppSettings());

    act(() => result.current.patch({ maxImageSizeMb: 250 }));

    expect(result.current.draft).toBeNull();
  });

  it('reset reverts the draft to the last saved value', async () => {
    mocked.getAppSettings.mockResolvedValue({ ...SETTINGS });
    const { result } = renderHook(() => useAppSettings());
    await waitFor(() => expect(result.current.draft).toEqual(SETTINGS));

    act(() => result.current.patch({ maxImageSizeMb: 999 }));
    expect(result.current.dirty).toBe(true);

    act(() => result.current.reset());

    expect(result.current.draft).toEqual(SETTINGS);
    expect(result.current.dirty).toBe(false);
  });

  it('save is a no-op when there is no draft yet', async () => {
    mocked.getAppSettings.mockReturnValue(new Promise<AppSettings>(() => {}));
    const { result } = renderHook(() => useAppSettings());

    await act(async () => {
      await result.current.save();
    });

    expect(mocked.saveAppSettings).not.toHaveBeenCalled();
    expect(result.current.isSaving).toBe(false);
  });

  it('saves the draft and updates saved+draft on success', async () => {
    mocked.getAppSettings.mockResolvedValue({ ...SETTINGS });
    const updated = { ...SETTINGS, maxImageSizeMb: 250 };
    mocked.saveAppSettings.mockResolvedValue(updated);
    const { result } = renderHook(() => useAppSettings());
    await waitFor(() => expect(result.current.draft).toEqual(SETTINGS));

    act(() => result.current.patch({ maxImageSizeMb: 250 }));
    await act(async () => {
      await result.current.save();
    });

    expect(mocked.saveAppSettings).toHaveBeenCalledWith(
      expect.objectContaining({ maxImageSizeMb: 250 }),
    );
    expect(result.current.draft).toEqual(updated);
    expect(result.current.dirty).toBe(false);
    expect(result.current.isSaving).toBe(false);
  });

  it('sets an error message when saving fails with an Error', async () => {
    mocked.getAppSettings.mockResolvedValue({ ...SETTINGS });
    mocked.saveAppSettings.mockRejectedValue(new Error('save boom'));
    const { result } = renderHook(() => useAppSettings());
    await waitFor(() => expect(result.current.draft).toEqual(SETTINGS));

    await act(async () => {
      await result.current.save();
    });

    expect(result.current.error).toBe('save boom');
    expect(result.current.isSaving).toBe(false);
  });

  it('falls back to a generic message when saving fails with a non-Error', async () => {
    mocked.getAppSettings.mockResolvedValue({ ...SETTINGS });
    mocked.saveAppSettings.mockRejectedValue('nope');
    const { result } = renderHook(() => useAppSettings());
    await waitFor(() => expect(result.current.draft).toEqual(SETTINGS));

    await act(async () => {
      await result.current.save();
    });

    expect(result.current.error).toBe('Failed to save settings');
  });

  it('refresh can be called manually to reload', async () => {
    mocked.getAppSettings.mockResolvedValue({ ...SETTINGS });
    const { result } = renderHook(() => useAppSettings());
    await waitFor(() => expect(result.current.draft).toEqual(SETTINGS));

    const updated = { ...SETTINGS, maxImageSizeMb: 300 };
    mocked.getAppSettings.mockResolvedValue(updated);
    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.draft).toEqual(updated);
    expect(result.current.error).toBeNull();
  });
});
