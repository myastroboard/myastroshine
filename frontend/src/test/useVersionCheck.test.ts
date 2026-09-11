import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useVersionCheck } from '@/hooks/useVersionCheck';
import { apiClient } from '@/services/api';
import type { VersionCheckResult } from '@/types';

vi.mock('@/services/api', () => ({
  apiClient: { checkForUpdates: vi.fn() },
}));

const mocked = vi.mocked(apiClient);

function result(overrides: Partial<VersionCheckResult>): VersionCheckResult {
  return {
    currentVersion: '1.0.0',
    latestVersion: null,
    updateAvailable: false,
    releaseUrl: null,
    releaseName: null,
    releaseNotes: null,
    publishedAt: null,
    error: null,
    ...overrides,
  };
}

describe('useVersionCheck', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('reports an update when the server flags one and the version is genuinely newer', async () => {
    mocked.checkForUpdates.mockResolvedValue(
      result({ currentVersion: '1.9.0', latestVersion: '2.0.0', updateAvailable: true }),
    );
    const { result: hook } = renderHook(() => useVersionCheck());

    await waitFor(() => expect(hook.current.updateAvailable).toBe(true));
    expect(hook.current.result?.latestVersion).toBe('2.0.0');
  });

  it('does not report an update when the server flag is true but the version is not newer', async () => {
    mocked.checkForUpdates.mockResolvedValue(
      result({ currentVersion: '1.0.0', latestVersion: '1.0.0', updateAvailable: true }),
    );
    const { result: hook } = renderHook(() => useVersionCheck());

    await waitFor(() => expect(hook.current.result).not.toBeNull());
    expect(hook.current.updateAvailable).toBe(false);
  });

  it('does not report an update when updateAvailable is false server-side', async () => {
    mocked.checkForUpdates.mockResolvedValue(
      result({ currentVersion: '1.0.0', latestVersion: '2.0.0', updateAvailable: false }),
    );
    const { result: hook } = renderHook(() => useVersionCheck());

    await waitFor(() => expect(hook.current.result).not.toBeNull());
    expect(hook.current.updateAvailable).toBe(false);
  });

  it('does not report an update when latestVersion is null', async () => {
    mocked.checkForUpdates.mockResolvedValue(
      result({ currentVersion: '1.0.0', latestVersion: null, updateAvailable: true }),
    );
    const { result: hook } = renderHook(() => useVersionCheck());

    await waitFor(() => expect(hook.current.result).not.toBeNull());
    expect(hook.current.updateAvailable).toBe(false);
  });

  it('correctly compares numerically and across differing part counts (v-prefix, short versions)', async () => {
    mocked.checkForUpdates.mockResolvedValue(
      result({ currentVersion: '1.9', latestVersion: 'v1.10.0', updateAvailable: true }),
    );
    const { result: hook } = renderHook(() => useVersionCheck());

    await waitFor(() => expect(hook.current.result).not.toBeNull());
    // Numeric compare: 10 > 9, not a lexical "1.10" < "1.9".
    expect(hook.current.updateAvailable).toBe(true);
  });

  it('treats a shorter latest version as equal when the missing part defaults to zero', async () => {
    mocked.checkForUpdates.mockResolvedValue(
      result({ currentVersion: '2.0.0', latestVersion: '2.0', updateAvailable: true }),
    );
    const { result: hook } = renderHook(() => useVersionCheck());

    await waitFor(() => expect(hook.current.result).not.toBeNull());
    // "2.0" has no third component - it defaults to 0, same as current's "2.0.0".
    expect(hook.current.updateAvailable).toBe(false);
  });

  it('treats a shorter current version as older when the extra part is non-zero', async () => {
    mocked.checkForUpdates.mockResolvedValue(
      result({ currentVersion: '1.2', latestVersion: '1.2.1', updateAvailable: true }),
    );
    const { result: hook } = renderHook(() => useVersionCheck());

    await waitFor(() => expect(hook.current.result).not.toBeNull());
    expect(hook.current.updateAvailable).toBe(true);
  });

  it('fails silently and leaves result null when the request rejects', async () => {
    mocked.checkForUpdates.mockRejectedValue(new Error('offline'));
    const { result: hook } = renderHook(() => useVersionCheck());

    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(hook.current.result).toBeNull();
    expect(hook.current.updateAvailable).toBe(false);
  });

  it('polls again after the interval elapses', async () => {
    vi.useFakeTimers();
    mocked.checkForUpdates.mockResolvedValue(result({}));

    renderHook(() => useVersionCheck());
    await vi.advanceTimersByTimeAsync(0);
    expect(mocked.checkForUpdates).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(4 * 60 * 60 * 1000);
    expect(mocked.checkForUpdates).toHaveBeenCalledTimes(2);
  });

  it('stops polling and ignores in-flight responses after unmount', async () => {
    vi.useFakeTimers();
    let resolveCheck!: (value: VersionCheckResult) => void;
    mocked.checkForUpdates.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCheck = resolve;
        }),
    );

    const { unmount } = renderHook(() => useVersionCheck());
    await vi.advanceTimersByTimeAsync(0);
    unmount();

    resolveCheck(result({ latestVersion: '9.9.9', updateAvailable: true }));
    await vi.advanceTimersByTimeAsync(4 * 60 * 60 * 1000 * 2);

    // No further polls after unmount cleared the interval.
    expect(mocked.checkForUpdates).toHaveBeenCalledTimes(1);
  });
});
