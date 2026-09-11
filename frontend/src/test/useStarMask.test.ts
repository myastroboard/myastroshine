import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useStarMask } from '@/hooks/useStarMask';
import { ApiError, apiClient } from '@/services/api';

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/api')>();
  return { ApiError: actual.ApiError, apiClient: { detectStars: vi.fn() } };
});

const mocked = vi.mocked(apiClient);

describe('useStarMask', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('starts with no stars and idle', () => {
    const { result } = renderHook(() => useStarMask('s1'));

    expect(result.current.stars).toEqual([]);
    expect(result.current.sourceCount).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('detects stars and stores the result', async () => {
    mocked.detectStars.mockResolvedValue({
      sessionId: 's1',
      sourceCount: 2,
      stars: [
        { x: 0.1, y: 0.2, radius: 0.01 },
        { x: 0.5, y: 0.5, radius: 0.02 },
      ],
    });
    const { result } = renderHook(() => useStarMask('s1'));

    await act(async () => {
      await result.current.detect(0.5, 20);
    });

    expect(mocked.detectStars).toHaveBeenCalledWith('s1', 0.5, 20);
    expect(result.current.stars).toHaveLength(2);
    expect(result.current.sourceCount).toBe(2);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('surfaces a friendly message on a 500', async () => {
    mocked.detectStars.mockRejectedValue(new ApiError(500, 'oops'));
    const { result } = renderHook(() => useStarMask('s1'));

    await act(async () => {
      await result.current.detect(0.5, 20);
    });

    expect(result.current.error).toBe('Something went wrong on the server. Try again in a moment.');
    expect(result.current.isLoading).toBe(false);
  });

  it('falls back to the default message for a non-Error failure', async () => {
    mocked.detectStars.mockRejectedValue('nope');
    const { result } = renderHook(() => useStarMask('s1'));

    await act(async () => {
      await result.current.detect(0.5, 20);
    });

    expect(result.current.error).toBe('Star detection failed');
  });

  it('clear resets stars, sourceCount, and error', async () => {
    mocked.detectStars.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useStarMask('s1'));

    await act(async () => {
      await result.current.detect(0.5, 20);
    });
    expect(result.current.error).toBe('boom');

    act(() => result.current.clear());

    expect(result.current.stars).toEqual([]);
    expect(result.current.sourceCount).toBeNull();
    expect(result.current.error).toBeNull();
  });
});
