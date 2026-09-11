import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useWatchStack } from '@/hooks/useWatchStack';
import { apiClient } from '@/services/api';
import type { StackResult } from '@/types';

vi.mock('@/services/api', () => ({
  apiClient: { getLatestWatchStack: vi.fn() },
}));

const mocked = vi.mocked(apiClient);

const STACK: StackResult = {
  stackId: 'stack-1',
  status: 'completed',
  jobId: null,
  wsStatusUrl: null,
  sessionId: null,
  stackedImageUrl: '/api/stack/stack-1/preview',
  statistics: null,
  frames: [],
  calibration: null,
  error: null,
};

describe('useWatchStack', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns null and does not poll while inactive', () => {
    const { result } = renderHook(() => useWatchStack(false));

    expect(result.current).toBeNull();
    expect(mocked.getLatestWatchStack).not.toHaveBeenCalled();
  });

  it('polls immediately and returns the latest watch stack while active', async () => {
    mocked.getLatestWatchStack.mockResolvedValue(STACK);
    const { result } = renderHook(() => useWatchStack(true));

    await waitFor(() => expect(result.current).toEqual(STACK));
    expect(mocked.getLatestWatchStack).toHaveBeenCalledTimes(1);
  });

  it('polls again every 15s', async () => {
    vi.useFakeTimers();
    mocked.getLatestWatchStack.mockResolvedValue(STACK);

    renderHook(() => useWatchStack(true));
    await vi.advanceTimersByTimeAsync(0);
    expect(mocked.getLatestWatchStack).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(15_000);
    expect(mocked.getLatestWatchStack).toHaveBeenCalledTimes(2);
  });

  it('swallows a failed poll and keeps the previous value', async () => {
    mocked.getLatestWatchStack.mockRejectedValue(new Error('offline'));
    const { result } = renderHook(() => useWatchStack(true));

    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(result.current).toBeNull();
  });

  it('returns null once toggled back to inactive, without clearing the underlying state', async () => {
    mocked.getLatestWatchStack.mockResolvedValue(STACK);
    const { result, rerender } = renderHook(({ active }) => useWatchStack(active), {
      initialProps: { active: true },
    });

    await waitFor(() => expect(result.current).toEqual(STACK));

    rerender({ active: false });
    expect(result.current).toBeNull();
  });

  it('stops polling and ignores a response that resolves after unmount', async () => {
    vi.useFakeTimers();
    let resolveFetch!: (value: StackResult) => void;
    mocked.getLatestWatchStack.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFetch = resolve;
        }),
    );

    const { unmount } = renderHook(() => useWatchStack(true));
    await vi.advanceTimersByTimeAsync(0);
    unmount();

    resolveFetch(STACK);
    await vi.advanceTimersByTimeAsync(30_000);

    // The interval was cleared on unmount - only the initial call happened.
    expect(mocked.getLatestWatchStack).toHaveBeenCalledTimes(1);
  });
});
