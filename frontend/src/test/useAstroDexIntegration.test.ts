import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAstroDexIntegration } from '@/hooks/useAstroDexIntegration';
import { apiClient } from '@/services/api';

vi.mock('@/services/api', () => ({
  apiClient: { returnToAstrodex: vi.fn() },
}));

const mocked = vi.mocked(apiClient);

describe('useAstroDexIntegration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('starts idle', () => {
    const { result } = renderHook(() => useAstroDexIntegration());

    expect(result.current.isLoading).toBe(false);
    expect(result.current.success).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('sends the session back to AstroDex and reports success', async () => {
    mocked.returnToAstrodex.mockResolvedValue({
      sessionId: 's1',
      status: 'received',
      astrodexItemId: 'item-1',
    });
    const { result } = renderHook(() => useAstroDexIntegration());

    let returned: boolean | undefined;
    await act(async () => {
      returned = await result.current.returnImage('s1');
    });

    expect(returned).toBe(true);
    expect(mocked.returnToAstrodex).toHaveBeenCalledWith('s1');
    expect(result.current.success).toBe(true);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('reflects isLoading true while the request is in flight', async () => {
    let resolve: (value: {
      sessionId: string;
      status: 'received';
      astrodexItemId: string;
    }) => void = () => {};
    mocked.returnToAstrodex.mockReturnValue(
      new Promise((r) => {
        resolve = r;
      }),
    );
    const { result } = renderHook(() => useAstroDexIntegration());

    let promise: Promise<boolean>;
    act(() => {
      promise = result.current.returnImage('s1');
    });

    await waitFor(() => expect(result.current.isLoading).toBe(true));

    await act(async () => {
      resolve({ sessionId: 's1', status: 'received', astrodexItemId: 'item-1' });
      await promise;
    });

    expect(result.current.isLoading).toBe(false);
  });

  it('sets an error message and returns false when the handoff fails with an Error', async () => {
    mocked.returnToAstrodex.mockRejectedValue(new Error('astrodex unreachable'));
    const { result } = renderHook(() => useAstroDexIntegration());

    let returned: boolean | undefined;
    await act(async () => {
      returned = await result.current.returnImage('s1');
    });

    expect(returned).toBe(false);
    expect(result.current.success).toBe(false);
    expect(result.current.error).toBe('astrodex unreachable');
    expect(result.current.isLoading).toBe(false);
  });

  it('falls back to a generic message when the handoff fails with a non-Error', async () => {
    mocked.returnToAstrodex.mockRejectedValue('boom');
    const { result } = renderHook(() => useAstroDexIntegration());

    await act(async () => {
      await result.current.returnImage('s1');
    });

    expect(result.current.error).toBe('Failed to send back to AstroDex');
  });

  it('resets success/error on a subsequent call', async () => {
    mocked.returnToAstrodex.mockRejectedValueOnce(new Error('first fails'));
    const { result } = renderHook(() => useAstroDexIntegration());

    await act(async () => {
      await result.current.returnImage('s1');
    });
    expect(result.current.error).toBe('first fails');

    mocked.returnToAstrodex.mockResolvedValueOnce({
      sessionId: 's1',
      status: 'received',
      astrodexItemId: 'item-1',
    });
    await act(async () => {
      await result.current.returnImage('s1');
    });

    expect(result.current.error).toBeNull();
    expect(result.current.success).toBe(true);
  });
});
