import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useCaptureInfo } from '@/hooks/useCaptureInfo';
import { apiClient } from '@/services/api';
import type { CaptureInfo } from '@/types';

vi.mock('@/services/api', () => ({
  apiClient: { getCaptureInfo: vi.fn() },
}));

const mocked = vi.mocked(apiClient);

describe('useCaptureInfo', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('stays null and skips the fetch when disabled', () => {
    const { result } = renderHook(() => useCaptureInfo('s1', false));

    expect(result.current).toBeNull();
    expect(mocked.getCaptureInfo).not.toHaveBeenCalled();
  });

  it('fetches capture info once enabled and mounted', async () => {
    const info: CaptureInfo = { objectName: 'M 31', frameCount: 100 };
    mocked.getCaptureInfo.mockResolvedValue(info);

    const { result } = renderHook(() => useCaptureInfo('s1', true));

    expect(result.current).toBeNull();
    await waitFor(() => expect(result.current).toEqual(info));
    expect(mocked.getCaptureInfo).toHaveBeenCalledWith('s1');
  });

  it('stays null when the session has no capture info', async () => {
    mocked.getCaptureInfo.mockResolvedValue(null);

    const { result } = renderHook(() => useCaptureInfo('s1', true));

    await waitFor(() => expect(mocked.getCaptureInfo).toHaveBeenCalled());
    expect(result.current).toBeNull();
  });

  it('stays null (rather than surfacing an error) when the request fails', async () => {
    mocked.getCaptureInfo.mockRejectedValue(new Error('boom'));

    const { result } = renderHook(() => useCaptureInfo('s1', true));

    await waitFor(() => expect(mocked.getCaptureInfo).toHaveBeenCalled());
    expect(result.current).toBeNull();
  });

  it('resets to null and refetches when the session changes', async () => {
    const infoA: CaptureInfo = { objectName: 'A' };
    const infoB: CaptureInfo = { objectName: 'B' };
    mocked.getCaptureInfo.mockResolvedValueOnce(infoA).mockResolvedValueOnce(infoB);

    const { result, rerender } = renderHook(
      ({ sessionId }) => useCaptureInfo(sessionId, true),
      { initialProps: { sessionId: 's1' } },
    );
    await waitFor(() => expect(result.current).toEqual(infoA));

    rerender({ sessionId: 's2' });

    await waitFor(() => expect(result.current).toEqual(infoB));
    expect(mocked.getCaptureInfo).toHaveBeenLastCalledWith('s2');
  });

  it('clears info once disabled again', async () => {
    const info: CaptureInfo = { objectName: 'M 31' };
    mocked.getCaptureInfo.mockResolvedValue(info);

    const { result, rerender } = renderHook(
      ({ enabled }) => useCaptureInfo('s1', enabled),
      { initialProps: { enabled: true } },
    );
    await waitFor(() => expect(result.current).toEqual(info));

    rerender({ enabled: false });

    expect(result.current).toBeNull();
  });

  it('ignores a stale response after the session changes before it resolves', async () => {
    let resolveFirst: (value: CaptureInfo | null) => void = () => {};
    mocked.getCaptureInfo.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveFirst = resolve;
        }),
    );
    const infoB: CaptureInfo = { objectName: 'B' };
    mocked.getCaptureInfo.mockResolvedValueOnce(infoB);

    const { result, rerender } = renderHook(
      ({ sessionId }) => useCaptureInfo(sessionId, true),
      { initialProps: { sessionId: 's1' } },
    );

    rerender({ sessionId: 's2' });
    await waitFor(() => expect(result.current).toEqual(infoB));

    // The stale first request now resolves - it must not overwrite infoB.
    resolveFirst({ objectName: 'A' });
    await Promise.resolve();

    expect(result.current).toEqual(infoB);
  });
});
