import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useImageProcessing } from '@/hooks/useImageProcessing';
import { apiClient } from '@/services/api';
import type { ProcessingStatus } from '@/types';

vi.mock('@/services/api', () => ({
  apiClient: { processImage: vi.fn() },
}));

/** A fake WebSocketClient whose status updates the test drives by hand. */
class FakeWs {
  static last: FakeWs | null = null;
  listeners = new Set<(s: ProcessingStatus) => void>();
  connected = false;
  disconnected = false;
  constructor() {
    FakeWs.last = this;
  }
  onStatusUpdate(listener: (s: ProcessingStatus) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
  connect(): void {
    this.connected = true;
  }
  disconnect(): void {
    this.disconnected = true;
  }
  emit(status: ProcessingStatus): void {
    this.listeners.forEach((listener) => listener(status));
  }
}

vi.mock('@/services/ws', () => ({
  processingStatusClient: vi.fn(() => new FakeWs()),
}));

const mocked = vi.mocked(apiClient);

function statusEvent(overrides: Partial<ProcessingStatus>): ProcessingStatus {
  return {
    jobId: 'job-1',
    status: 'processing',
    progressPercent: 0,
    currentStep: '',
    error: null,
    ...overrides,
  } as ProcessingStatus;
}

describe('useImageProcessing.trackJob', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    FakeWs.last = null;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('waits for the WebSocket "completed" before bumping previewVersion (queue mode)', async () => {
    const { result } = renderHook(() => useImageProcessing('s1'));
    expect(result.current.previewVersion).toBe(0);

    // A queued job - the backend has not processed the image yet.
    act(() => {
      result.current.trackJob({
        sessionId: 's1',
        jobId: 'job-1',
        status: 'queued',
        previewUrl: '/api/preview/s1',
        estimatedTimeSeconds: 8,
        wsStatusUrl: '/ws/processing-status/job-1',
      });
    });

    // Nothing has finished yet: the preview must not refetch.
    expect(result.current.previewVersion).toBe(0);
    expect(result.current.status).toBe('processing');
    expect(FakeWs.last?.connected).toBe(true);

    act(() => FakeWs.last?.emit(statusEvent({ status: 'completed', progressPercent: 100 })));

    await waitFor(() => expect(result.current.previewVersion).toBe(1));
    expect(result.current.status).toBe('completed');
  });

  it('bumps previewVersion at once when the job is already completed (sync mode)', () => {
    const { result } = renderHook(() => useImageProcessing('s1'));

    act(() => {
      result.current.trackJob({
        sessionId: 's1',
        jobId: 'job-1',
        status: 'completed',
        previewUrl: '/api/preview/s1',
        estimatedTimeSeconds: 0,
        wsStatusUrl: '/ws/processing-status/job-1',
      });
    });

    expect(result.current.previewVersion).toBe(1);
    expect(result.current.status).toBe('completed');
  });

  it('surfaces a failed job as an error and stops', async () => {
    const { result } = renderHook(() => useImageProcessing('s1'));

    act(() => {
      result.current.trackJob({
        sessionId: 's1',
        jobId: 'job-1',
        status: 'queued',
        previewUrl: '/api/preview/s1',
        estimatedTimeSeconds: 8,
        wsStatusUrl: '/ws/processing-status/job-1',
      });
    });
    act(() => FakeWs.last?.emit(statusEvent({ status: 'failed', error: 'boom' })));

    await waitFor(() => expect(result.current.error).toBe('boom'));
    expect(result.current.previewVersion).toBe(0);
  });

  it('applyParameters routes through the same job tracking', async () => {
    mocked.processImage.mockResolvedValue({
      sessionId: 's1',
      jobId: 'job-9',
      status: 'queued',
      previewUrl: '/api/preview/s1',
      estimatedTimeSeconds: 8,
      wsStatusUrl: '/ws/processing-status/job-9',
    });

    const { result } = renderHook(() => useImageProcessing('s1'));

    await act(async () => {
      await result.current.applyParameters({ ...result.current.parameters });
    });

    expect(result.current.previewVersion).toBe(0); // still queued
    act(() => FakeWs.last?.emit(statusEvent({ jobId: 'job-9', status: 'completed' })));
    await waitFor(() => expect(result.current.previewVersion).toBe(1));
  });

  it('coalesces a burst: one job in flight, the latest change sent on settle', async () => {
    let n = 0;
    mocked.processImage.mockImplementation(() =>
      Promise.resolve({
        sessionId: 's1',
        jobId: `job-${(n += 1)}`,
        status: 'queued',
        previewUrl: '/api/preview/s1',
        estimatedTimeSeconds: 8,
        wsStatusUrl: `/ws/processing-status/job-${n}`,
      }),
    );

    const { result } = renderHook(() => useImageProcessing('s1'));

    // Three rapid edits while the first request is still resolving.
    await act(async () => {
      void result.current.applyParameters({ ...result.current.parameters, contrast: 1.1 });
      void result.current.applyParameters({ ...result.current.parameters, contrast: 1.2 });
      void result.current.applyParameters({ ...result.current.parameters, contrast: 1.3 });
    });

    // Only the first went to the backend; the other two were coalesced.
    expect(mocked.processImage).toHaveBeenCalledTimes(1);

    // First job finishes -> the coalesced (latest) edit is sent, once.
    await act(async () => {
      FakeWs.last?.emit(statusEvent({ status: 'completed' }));
    });
    await waitFor(() => expect(mocked.processImage).toHaveBeenCalledTimes(2));
    expect(mocked.processImage).toHaveBeenLastCalledWith(
      's1',
      expect.objectContaining({ contrast: 1.3 }),
    );
  });

  it('proceeds anyway when the in-flight job has gone silent for too long', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    try {
      let n = 0;
      mocked.processImage.mockImplementation(() =>
        Promise.resolve({
          sessionId: 's1',
          jobId: `job-${(n += 1)}`,
          status: 'queued',
          previewUrl: '/api/preview/s1',
          estimatedTimeSeconds: 8,
          wsStatusUrl: `/ws/processing-status/job-${n}`,
        }),
      );

      const { result } = renderHook(() => useImageProcessing('s1'));

      await act(async () => {
        void result.current.applyParameters({ ...result.current.parameters, contrast: 1.1 });
      });
      expect(mocked.processImage).toHaveBeenCalledTimes(1);

      // The job never reports back. A second edit lands 10s later - coalesced.
      vi.advanceTimersByTime(10_000);
      await act(async () => {
        void result.current.applyParameters({ ...result.current.parameters, contrast: 1.2 });
      });
      expect(mocked.processImage).toHaveBeenCalledTimes(1);

      // Still silent 50s in - a further edit stops waiting and goes out.
      vi.advanceTimersByTime(50_000);
      await act(async () => {
        void result.current.applyParameters({ ...result.current.parameters, contrast: 1.3 });
      });
      expect(mocked.processImage).toHaveBeenCalledTimes(2);
      expect(mocked.processImage).toHaveBeenLastCalledWith(
        's1',
        expect.objectContaining({ contrast: 1.3 }),
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it('updateParameter updates the value live but defers the render until release', async () => {
    mocked.processImage.mockResolvedValue({
      sessionId: 's1',
      jobId: 'job-1',
      status: 'queued',
      previewUrl: '/api/preview/s1',
      estimatedTimeSeconds: 8,
      wsStatusUrl: '/ws/processing-status/job-1',
    });

    const { result } = renderHook(() => useImageProcessing('s1'));

    act(() => result.current.updateParameter('contrast', 1.5));
    act(() => result.current.updateParameter('contrast', 1.9));

    expect(result.current.parameters.contrast).toBe(1.9); // the slider tracks live
    expect(mocked.processImage).not.toHaveBeenCalled(); // ...but nothing rendered

    await act(async () => {
      document.dispatchEvent(new Event('pointerup'));
    });

    await waitFor(() => expect(mocked.processImage).toHaveBeenCalledTimes(1));
    expect(mocked.processImage).toHaveBeenCalledWith(
      's1',
      expect.objectContaining({ contrast: 1.9 }),
    );
  });

  it('falls back to a timer when no release event ever arrives', async () => {
    vi.useFakeTimers();
    try {
      mocked.processImage.mockResolvedValue({
        sessionId: 's1',
        jobId: 'job-1',
        status: 'queued',
        previewUrl: '/api/preview/s1',
        estimatedTimeSeconds: 8,
        wsStatusUrl: '/ws/processing-status/job-1',
      });

      const { result } = renderHook(() => useImageProcessing('s1'));
      act(() => result.current.updateParameter('exposure', 0.4));
      expect(mocked.processImage).not.toHaveBeenCalled();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1200);
      });
      expect(mocked.processImage).toHaveBeenCalledWith(
        's1',
        expect.objectContaining({ exposure: 0.4 }),
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it('a superseded job releases the slot and flushes the pending edit', async () => {
    let n = 0;
    mocked.processImage.mockImplementation(() =>
      Promise.resolve({
        sessionId: 's1',
        jobId: `job-${(n += 1)}`,
        status: 'queued',
        previewUrl: '/api/preview/s1',
        estimatedTimeSeconds: 8,
        wsStatusUrl: `/ws/processing-status/job-${n}`,
      }),
    );

    const { result } = renderHook(() => useImageProcessing('s1'));

    await act(async () => {
      void result.current.applyParameters({ ...result.current.parameters, exposure: 0.1 });
      void result.current.applyParameters({ ...result.current.parameters, exposure: 0.2 });
    });
    expect(mocked.processImage).toHaveBeenCalledTimes(1);

    await act(async () => {
      FakeWs.last?.emit(statusEvent({ status: 'superseded' }));
    });
    await waitFor(() => expect(mocked.processImage).toHaveBeenCalledTimes(2));
    expect(mocked.processImage).toHaveBeenLastCalledWith(
      's1',
      expect.objectContaining({ exposure: 0.2 }),
    );
  });
});
