import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAutoAstro } from '@/hooks/useAutoAstro';
import { ApiError, apiClient } from '@/services/api';
import { DEFAULT_PARAMETERS } from '@/types';

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/api')>();
  return { ...actual, apiClient: { applyAutoAstro: vi.fn() } };
});

const mocked = vi.mocked(apiClient);

describe('useAutoAstro', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('starts idle', () => {
    const { result } = renderHook(() => useAutoAstro('s1'));

    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('applies auto astro and returns the result', async () => {
    mocked.applyAutoAstro.mockResolvedValue({
      sessionId: 's1',
      jobId: 'job-1',
      status: 'completed',
      previewUrl: '/api/preview/s1',
      estimatedTimeSeconds: 0,
      wsStatusUrl: '/ws/processing-status/job-1',
      parameters: DEFAULT_PARAMETERS,
    });
    const { result } = renderHook(() => useAutoAstro('s1'));

    let returned;
    await act(async () => {
      returned = await result.current.apply();
    });

    expect(mocked.applyAutoAstro).toHaveBeenCalledWith('s1');
    expect(returned).toMatchObject({ jobId: 'job-1' });
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('surfaces a friendly message and returns null on a 503', async () => {
    mocked.applyAutoAstro.mockRejectedValue(new ApiError(503, 'down for maintenance'));
    const { result } = renderHook(() => useAutoAstro('s1'));

    let returned;
    await act(async () => {
      returned = await result.current.apply();
    });

    expect(returned).toBeNull();
    expect(result.current.error).toBe('The server is temporarily unavailable - try again shortly.');
    expect(result.current.isLoading).toBe(false);
  });

  it('falls back to the error message for a plain Error', async () => {
    mocked.applyAutoAstro.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useAutoAstro('s1'));

    await act(async () => {
      await result.current.apply();
    });

    expect(result.current.error).toBe('boom');
  });

  it('falls back to the provided default when the failure is not an Error', async () => {
    mocked.applyAutoAstro.mockRejectedValue('nope');
    const { result } = renderHook(() => useAutoAstro('s1'));

    await act(async () => {
      await result.current.apply();
    });

    expect(result.current.error).toBe('Auto Astro failed');
  });
});
