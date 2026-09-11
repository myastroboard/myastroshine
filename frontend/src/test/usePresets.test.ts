import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { usePresets } from '@/hooks/usePresets';
import { apiClient } from '@/services/api';
import { DEFAULT_PARAMETERS, type Preset } from '@/types';

vi.mock('@/services/api', () => ({
  apiClient: {
    listPresets: vi.fn(),
    applyPreset: vi.fn(),
    savePreset: vi.fn(),
    deletePreset: vi.fn(),
  },
}));

const mocked = vi.mocked(apiClient);

const PRESET: Preset = {
  presetId: 'p1',
  name: 'My preset',
  category: 'custom',
  description: '',
  parameters: DEFAULT_PARAMETERS,
  author: 'me',
  isFavorite: false,
};

describe('usePresets', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.listPresets.mockResolvedValue({ presets: [PRESET], total: 1 });
  });

  it('loads presets on mount', async () => {
    const { result } = renderHook(() => usePresets('s1'));

    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.presets).toEqual([PRESET]);
    expect(result.current.activePreset).toBeUndefined();
  });

  it('leaves the current list in place when refreshing fails', async () => {
    mocked.listPresets.mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => usePresets('s1'));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.presets).toEqual([]);
  });

  it('applyPreset marks it active and returns the job handle', async () => {
    mocked.applyPreset.mockResolvedValue({
      sessionId: 's1',
      jobId: 'job-1',
      status: 'queued',
      previewUrl: '/api/preview/s1',
      estimatedTimeSeconds: 5,
      wsStatusUrl: '/ws/processing-status/job-1',
    });
    const { result } = renderHook(() => usePresets('s1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    let job;
    await act(async () => {
      job = await result.current.applyPreset('p1');
    });

    expect(result.current.activePreset).toBe('p1');
    expect(mocked.applyPreset).toHaveBeenCalledWith('p1', 's1');
    expect(job).toMatchObject({ jobId: 'job-1' });
  });

  it('savePreset saves then refreshes the list', async () => {
    mocked.savePreset.mockResolvedValue({
      presetId: 'p2',
      name: 'New preset',
      createdAt: '2026-09-11T00:00:00Z',
    });
    const { result } = renderHook(() => usePresets('s1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    mocked.listPresets.mockResolvedValue({
      presets: [PRESET, { ...PRESET, presetId: 'p2', name: 'New preset' }],
      total: 2,
    });

    await act(async () => {
      await result.current.savePreset({
        name: 'New preset',
        parameters: DEFAULT_PARAMETERS,
      });
    });

    expect(mocked.savePreset).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'New preset' }),
    );
    expect(mocked.listPresets).toHaveBeenCalledTimes(2); // initial + post-save refresh
    expect(result.current.presets).toHaveLength(2);
  });

  it('deletePreset clears the active highlight only when it matches, then refreshes', async () => {
    mocked.applyPreset.mockResolvedValue({
      sessionId: 's1',
      jobId: 'job-1',
      status: 'queued',
      previewUrl: '/api/preview/s1',
      estimatedTimeSeconds: 5,
      wsStatusUrl: '/ws/processing-status/job-1',
    });
    mocked.deletePreset.mockResolvedValue(undefined);
    const { result } = renderHook(() => usePresets('s1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.applyPreset('p1');
    });
    expect(result.current.activePreset).toBe('p1');

    mocked.listPresets.mockResolvedValue({ presets: [], total: 0 });
    await act(async () => {
      await result.current.deletePreset('p1');
    });

    expect(mocked.deletePreset).toHaveBeenCalledWith('p1');
    expect(result.current.activePreset).toBeUndefined();
    expect(result.current.presets).toEqual([]);
  });

  it('deletePreset leaves an unrelated active preset untouched', async () => {
    mocked.applyPreset.mockResolvedValue({
      sessionId: 's1',
      jobId: 'job-1',
      status: 'queued',
      previewUrl: '/api/preview/s1',
      estimatedTimeSeconds: 5,
      wsStatusUrl: '/ws/processing-status/job-1',
    });
    mocked.deletePreset.mockResolvedValue(undefined);
    const { result } = renderHook(() => usePresets('s1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.applyPreset('p1');
    });

    await act(async () => {
      await result.current.deletePreset('other-preset');
    });

    expect(result.current.activePreset).toBe('p1');
  });

  it('clearActivePreset drops the highlight', async () => {
    mocked.applyPreset.mockResolvedValue({
      sessionId: 's1',
      jobId: 'job-1',
      status: 'queued',
      previewUrl: '/api/preview/s1',
      estimatedTimeSeconds: 5,
      wsStatusUrl: '/ws/processing-status/job-1',
    });
    const { result } = renderHook(() => usePresets('s1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.applyPreset('p1');
    });
    expect(result.current.activePreset).toBe('p1');

    act(() => result.current.clearActivePreset());

    expect(result.current.activePreset).toBeUndefined();
  });

  it('refresh can be triggered manually', async () => {
    const { result } = renderHook(() => usePresets('s1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    mocked.listPresets.mockResolvedValue({ presets: [], total: 0 });
    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.presets).toEqual([]);
  });
});
