import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useDepthShift } from '@/hooks/useDepthShift';
import { ApiError, apiClient } from '@/services/api';

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/api')>();
  return { ApiError: actual.ApiError, apiClient: { generateDepthShift: vi.fn() } };
});

const mocked = vi.mocked(apiClient);

describe('useDepthShift', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('starts with no layers, default intensity, and idle', () => {
    const { result } = renderHook(() => useDepthShift('s1'));

    expect(result.current.layerUrls).toEqual([]);
    expect(result.current.statistics).toBeNull();
    expect(result.current.intensity).toBe(50);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('setIntensity updates the value used by generate', async () => {
    mocked.generateDepthShift.mockResolvedValue({
      sessionId: 's1',
      numLayers: 7,
      depthMapUrl: '/depth.png',
      depthLayers: [],
      statistics: {
        minDepth: 0,
        maxDepth: 1,
        meanDepth: 0.5,
        medianDepth: 0.5,
        brightAreasPercent: 10,
      },
    });
    const { result } = renderHook(() => useDepthShift('s1'));

    act(() => result.current.setIntensity(80));
    expect(result.current.intensity).toBe(80);

    await act(async () => {
      await result.current.generate();
    });

    expect(mocked.generateDepthShift).toHaveBeenCalledWith('s1', 7, 80, undefined);
  });

  it('generate defaults numLayers to 7 and passes an explicit focus point through', async () => {
    mocked.generateDepthShift.mockResolvedValue({
      sessionId: 's1',
      numLayers: 3,
      depthMapUrl: '/depth.png',
      depthLayers: [
        { layerId: 0, depthRange: [0, 1], imageUrl: '/layer0.png' },
        { layerId: 1, depthRange: [1, 2], imageUrl: '/layer1.png' },
      ],
      statistics: {
        minDepth: 0,
        maxDepth: 1,
        meanDepth: 0.5,
        medianDepth: 0.5,
        brightAreasPercent: 20,
      },
    });
    const { result } = renderHook(() => useDepthShift('s1'));

    await act(async () => {
      await result.current.generate(3, { x: 0.4, y: 0.6 });
    });

    expect(mocked.generateDepthShift).toHaveBeenCalledWith('s1', 3, 50, { x: 0.4, y: 0.6 });
    expect(result.current.layerUrls).toEqual(['/layer0.png', '/layer1.png']);
    expect(result.current.statistics).toMatchObject({ brightAreasPercent: 20 });
    expect(result.current.isLoading).toBe(false);
  });

  it('surfaces a friendly message on a 429', async () => {
    mocked.generateDepthShift.mockRejectedValue(new ApiError(429, 'slow down'));
    const { result } = renderHook(() => useDepthShift('s1'));

    await act(async () => {
      await result.current.generate();
    });

    expect(result.current.error).toBe('The server is busy - wait a moment and try again.');
    expect(result.current.isLoading).toBe(false);
  });

  it('falls back to the default message for a non-Error failure', async () => {
    mocked.generateDepthShift.mockRejectedValue('nope');
    const { result } = renderHook(() => useDepthShift('s1'));

    await act(async () => {
      await result.current.generate();
    });

    expect(result.current.error).toBe('Depth shift failed');
  });
});
