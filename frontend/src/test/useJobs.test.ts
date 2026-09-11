import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useJobs } from '@/hooks/useJobs';
import { apiClient } from '@/services/api';
import type { DiskUsage, JobListResult } from '@/types';

vi.mock('@/services/api', () => ({
  apiClient: {
    getJobs: vi.fn(),
    getDiskUsage: vi.fn(),
  },
}));

const mocked = vi.mocked(apiClient);

const JOB_LIST: JobListResult = {
  jobs: [
    {
      jobId: 'job-1',
      sessionId: 's1',
      status: 'completed',
      progressPercent: 100,
      currentStep: null,
      error: null,
      createdAt: '2026-09-11T10:00:00Z',
      updatedAt: '2026-09-11T10:00:01Z',
    },
  ],
  total: 1,
  limit: 25,
  offset: 0,
};

const DISK_USAGE: DiskUsage = {
  totalBytes: 100,
  usedBytes: 40,
  freeBytes: 60,
  imagesBytes: 1,
  stacksBytes: 2,
  dbBytes: 3,
  logsBytes: 4,
};

describe('useJobs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.getJobs.mockResolvedValue(JOB_LIST);
    mocked.getDiskUsage.mockResolvedValue(DISK_USAGE);
  });

  it('loads jobs and disk usage on mount', async () => {
    const { result } = renderHook(() => useJobs());

    expect(result.current.isLoading).toBe(true);

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.jobs).toEqual(JOB_LIST.jobs);
    expect(result.current.total).toBe(1);
    expect(result.current.diskUsage).toEqual(DISK_USAGE);
    expect(result.current.error).toBeNull();
    expect(mocked.getJobs).toHaveBeenCalledWith({ status: undefined, limit: 25, offset: 0 });
  });

  it('surfaces an Error instance message on failure', async () => {
    mocked.getJobs.mockRejectedValue(new Error('network down'));
    const { result } = renderHook(() => useJobs());

    await waitFor(() => expect(result.current.error).toBe('network down'));
    expect(result.current.isLoading).toBe(false);
  });

  it('falls back to a generic message when a non-Error is thrown', async () => {
    mocked.getDiskUsage.mockRejectedValue('boom');
    const { result } = renderHook(() => useJobs());

    await waitFor(() => expect(result.current.error).toBe('Failed to load job history'));
  });

  it('changeStatus updates the filter and resets to the first page', async () => {
    const { result } = renderHook(() => useJobs());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => result.current.setOffset(25));
    expect(result.current.offset).toBe(25);

    act(() => result.current.setStatus('failed'));

    expect(result.current.status).toBe('failed');
    expect(result.current.offset).toBe(0);
    await waitFor(() =>
      expect(mocked.getJobs).toHaveBeenLastCalledWith({
        status: 'failed',
        limit: 25,
        offset: 0,
      }),
    );
  });

  it('refresh can be called directly to reload', async () => {
    const { result } = renderHook(() => useJobs());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    mocked.getJobs.mockClear();
    await act(async () => {
      await result.current.refresh();
    });
    expect(mocked.getJobs).toHaveBeenCalledTimes(1);
  });
});
