import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useLogs } from '@/hooks/useLogs';
import { apiClient } from '@/services/api';
import type { LogLevels, LogTail } from '@/types';

vi.mock('@/services/api', () => ({
  apiClient: {
    getLogs: vi.fn(),
    getLogLevels: vi.fn(),
    clearLogs: vi.fn(),
    exportLogs: vi.fn(),
  },
}));

const mocked = vi.mocked(apiClient);

const TAIL: LogTail = { lines: ['line one', 'line two'], returned: 2, filteredLevel: null };
const LEVELS: LogLevels = { file: 'info', console: 'warning' };

describe('useLogs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.getLogs.mockResolvedValue(TAIL);
    mocked.getLogLevels.mockResolvedValue(LEVELS);
  });

  it('loads the log tail and levels on mount', async () => {
    const { result } = renderHook(() => useLogs());

    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.lines).toEqual(TAIL.lines);
    expect(result.current.levels).toEqual(LEVELS);
    expect(result.current.error).toBeNull();
    expect(mocked.getLogs).toHaveBeenCalledWith(300, undefined);
  });

  it('re-fetches with the selected level filter', async () => {
    const { result } = renderHook(() => useLogs());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => result.current.setLevel('error'));

    await waitFor(() => expect(mocked.getLogs).toHaveBeenLastCalledWith(300, 'error'));
  });

  it('surfaces an Error instance message on failure', async () => {
    mocked.getLogs.mockRejectedValue(new Error('logs unavailable'));
    const { result } = renderHook(() => useLogs());

    await waitFor(() => expect(result.current.error).toBe('logs unavailable'));
  });

  it('falls back to a generic message when a non-Error is thrown', async () => {
    mocked.getLogLevels.mockRejectedValue('boom');
    const { result } = renderHook(() => useLogs());

    await waitFor(() => expect(result.current.error).toBe('Failed to load logs'));
  });

  it('clear() wipes the log file and reloads, toggling busy', async () => {
    mocked.clearLogs.mockResolvedValue(undefined);
    const { result } = renderHook(() => useLogs());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    mocked.getLogs.mockClear();
    let clearPromise!: Promise<void>;
    act(() => {
      clearPromise = result.current.clear();
    });
    expect(result.current.busy).toBe(true);

    await act(async () => {
      await clearPromise;
    });

    expect(result.current.busy).toBe(false);
    expect(mocked.clearLogs).toHaveBeenCalledTimes(1);
    expect(mocked.getLogs).toHaveBeenCalledTimes(1); // refresh() ran after clearing
  });

  it('clear() still releases busy when the clear call fails', async () => {
    mocked.clearLogs.mockRejectedValue(new Error('nope'));
    const { result } = renderHook(() => useLogs());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await expect(
      act(async () => {
        await result.current.clear();
      }),
    ).rejects.toThrow('nope');

    expect(result.current.busy).toBe(false);
  });

  it('exportZip triggers a download of the returned blob and revokes the URL', async () => {
    const blob = new Blob(['zip-bytes']);
    mocked.exportLogs.mockResolvedValue(blob);

    const objectUrl = 'blob:mock-url';
    const createObjectURL = vi.fn().mockReturnValue(objectUrl);
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', { ...URL, createObjectURL, revokeObjectURL });

    const clickSpy = vi.fn();
    const anchor = document.createElement('a');
    vi.spyOn(anchor, 'click').mockImplementation(clickSpy);
    const createElementSpy = vi
      .spyOn(document, 'createElement')
      .mockReturnValue(anchor as unknown as HTMLElement);

    const { result } = renderHook(() => useLogs());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.exportZip();
    });

    expect(mocked.exportLogs).toHaveBeenCalledTimes(1);
    expect(createObjectURL).toHaveBeenCalledWith(blob);
    expect(anchor.href).toBe(objectUrl);
    expect(anchor.download).toBe('myastroshine-logs.zip');
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith(objectUrl);

    createElementSpy.mockRestore();
    vi.unstubAllGlobals();
  });
});
