import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useImageProcessing } from '@/hooks/useImageProcessing';
import { apiClient, ApiError } from '@/services/api';
import type { ProcessingStatus } from '@/types';

vi.mock('@/services/api', () => {
  class ApiError extends Error {
    constructor(
      public status: number,
      message: string,
    ) {
      super(message);
      this.name = 'ApiError';
    }
  }
  return {
    apiClient: { processImage: vi.fn() },
    ApiError,
  };
});

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

  it('remembers a slider value before an edit run and reverts to it', async () => {
    mocked.processImage.mockResolvedValue({
      sessionId: 's1',
      jobId: 'job-1',
      status: 'queued',
      previewUrl: '/api/preview/s1',
      estimatedTimeSeconds: 8,
      wsStatusUrl: '/ws/processing-status/job-1',
    });

    const { result } = renderHook(() => useImageProcessing('s1'));
    expect(result.current.sliderRevert).toBeNull();

    act(() => result.current.updateParameter('contrast', 1.5));
    act(() => result.current.updateParameter('contrast', 1.8));
    // captured once, at the value before the run (DEFAULT contrast is 1.0)
    expect(result.current.sliderRevert).toEqual({ key: 'contrast', value: 1.0 });

    await act(async () => {
      result.current.revertSlider();
    });
    expect(result.current.parameters.contrast).toBe(1.0);
    expect(result.current.sliderRevert).toBeNull();
    await waitFor(() =>
      expect(mocked.processImage).toHaveBeenCalledWith(
        's1',
        expect.objectContaining({ contrast: 1.0 }),
      ),
    );
  });

  it('moves the revert target to whichever slider is touched, and a reset clears it', () => {
    const { result } = renderHook(() => useImageProcessing('s1'));

    act(() => result.current.updateParameter('contrast', 1.5));
    act(() => result.current.updateParameter('exposure', 0.3));
    expect(result.current.sliderRevert).toEqual({ key: 'exposure', value: 0 });

    act(() => result.current.resetParameters());
    expect(result.current.sliderRevert).toBeNull();
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

  it('falls back to a generic message when a failed WebSocket update carries no error text', async () => {
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
    act(() => FakeWs.last?.emit(statusEvent({ status: 'failed', error: undefined })));

    await waitFor(() => expect(result.current.error).toBe('Processing failed'));
  });

  it('a release event with nothing held is a harmless no-op', () => {
    const { result } = renderHook(() => useImageProcessing('s1'));

    act(() => {
      document.dispatchEvent(new Event('pointerup'));
    });

    expect(result.current.status).toBe('idle');
    expect(mocked.processImage).not.toHaveBeenCalled();
  });

  it('updates progress and step from an in-progress WebSocket update without settling the job', () => {
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

    act(() =>
      FakeWs.last?.emit(
        statusEvent({ status: 'processing', progressPercent: 42, currentStep: 'denoise' }),
      ),
    );

    expect(result.current.status).toBe('processing');
    expect(result.current.progress).toBe(42);
    expect(result.current.currentStep).toBe('denoise');
    expect(result.current.previewVersion).toBe(0);
    expect(FakeWs.last?.disconnected).toBe(false);
  });

  it('trackJob handles an already-failed response with no WebSocket (sync mode)', () => {
    const { result } = renderHook(() => useImageProcessing('s1'));

    act(() => {
      result.current.trackJob({
        sessionId: 's1',
        jobId: 'job-1',
        status: 'failed',
        previewUrl: '/api/preview/s1',
        estimatedTimeSeconds: 0,
        wsStatusUrl: '/ws/processing-status/job-1',
      });
    });

    expect(result.current.status).toBe('failed');
    expect(result.current.error).toBe('Processing failed');
    expect(result.current.previewVersion).toBe(0);
  });

  it('disconnects the previous job socket when a new job starts', () => {
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
    const firstWs = FakeWs.last;

    act(() => {
      result.current.trackJob({
        sessionId: 's1',
        jobId: 'job-2',
        status: 'queued',
        previewUrl: '/api/preview/s1',
        estimatedTimeSeconds: 8,
        wsStatusUrl: '/ws/processing-status/job-2',
      });
    });

    expect(firstWs?.disconnected).toBe(true);
    expect(FakeWs.last).not.toBe(firstWs);
  });

  it('disconnects the socket on unmount', () => {
    const { result, unmount } = renderHook(() => useImageProcessing('s1'));

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

    unmount();
    expect(FakeWs.last?.disconnected).toBe(true);
  });

  it('surfaces a plain network error message and clears busy so the next edit proceeds', async () => {
    mocked.processImage.mockRejectedValueOnce(new Error('Failed to fetch'));

    const { result } = renderHook(() => useImageProcessing('s1'));

    await act(async () => {
      await result.current.applyParameters({ ...result.current.parameters, exposure: 0.2 });
    });

    expect(result.current.status).toBe('failed');
    expect(result.current.error).toBe('Failed to fetch');

    // busy was released - a further edit is sent right away, not coalesced.
    mocked.processImage.mockResolvedValueOnce({
      sessionId: 's1',
      jobId: 'job-2',
      status: 'queued',
      previewUrl: '/api/preview/s1',
      estimatedTimeSeconds: 8,
      wsStatusUrl: '/ws/processing-status/job-2',
    });
    await act(async () => {
      await result.current.applyParameters({ ...result.current.parameters, exposure: 0.3 });
    });
    expect(mocked.processImage).toHaveBeenCalledTimes(2);
  });

  it('translates a 503 ApiError into the friendly "server unavailable" message', async () => {
    mocked.processImage.mockRejectedValueOnce(new ApiError(503, 'Service Unavailable'));

    const { result } = renderHook(() => useImageProcessing('s1'));

    await act(async () => {
      await result.current.applyParameters({ ...result.current.parameters, exposure: 0.2 });
    });

    expect(result.current.error).toBe(
      'The server is temporarily unavailable - try again shortly.',
    );
  });

  it('flushes a queued edit from the catch handler when the in-flight request itself fails', async () => {
    let reject1!: (err: unknown) => void;
    let n = 0;
    mocked.processImage.mockImplementationOnce(
      () =>
        new Promise((_resolve, reject) => {
          reject1 = reject;
        }),
    );

    const { result } = renderHook(() => useImageProcessing('s1'));

    act(() => {
      void result.current.applyParameters({ ...result.current.parameters, exposure: 0.1 });
    });
    expect(mocked.processImage).toHaveBeenCalledTimes(1);

    act(() => {
      void result.current.applyParameters({ ...result.current.parameters, exposure: 0.2 });
    });
    expect(mocked.processImage).toHaveBeenCalledTimes(1); // coalesced, still in flight

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

    await act(async () => {
      reject1(new Error('boom'));
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(() => expect(mocked.processImage).toHaveBeenCalledTimes(2));
    expect(mocked.processImage).toHaveBeenLastCalledWith(
      's1',
      expect.objectContaining({ exposure: 0.2 }),
    );
  });

  it('revertSlider is a no-op when no slider is currently held', () => {
    const { result } = renderHook(() => useImageProcessing('s1'));

    act(() => result.current.revertSlider());

    expect(result.current.sliderRevert).toBeNull();
    expect(mocked.processImage).not.toHaveBeenCalled();
  });

  it('updateStarRemovalEngine applies immediately, uncoalesced', async () => {
    mocked.processImage.mockResolvedValue({
      sessionId: 's1',
      jobId: 'job-1',
      status: 'queued',
      previewUrl: '/api/preview/s1',
      estimatedTimeSeconds: 8,
      wsStatusUrl: '/ws/processing-status/job-1',
    });
    const { result } = renderHook(() => useImageProcessing('s1'));

    await act(async () => {
      result.current.updateStarRemovalEngine('starnet2');
    });

    expect(result.current.parameters.starRemovalEngine).toBe('starnet2');
    expect(mocked.processImage).toHaveBeenCalledWith(
      's1',
      expect.objectContaining({ starRemovalEngine: 'starnet2' }),
    );
  });

  it('updateDenoiseEngine applies immediately, uncoalesced', async () => {
    mocked.processImage.mockResolvedValue({
      sessionId: 's1',
      jobId: 'job-1',
      status: 'queued',
      previewUrl: '/api/preview/s1',
      estimatedTimeSeconds: 8,
      wsStatusUrl: '/ws/processing-status/job-1',
    });
    const { result } = renderHook(() => useImageProcessing('s1'));

    await act(async () => {
      result.current.updateDenoiseEngine('deepsnr');
    });

    expect(result.current.parameters.denoiseEngine).toBe('deepsnr');
    expect(mocked.processImage).toHaveBeenCalledWith(
      's1',
      expect.objectContaining({ denoiseEngine: 'deepsnr' }),
    );
  });

  it('updateStackParameter updates live and defers the render like a slider', async () => {
    mocked.processImage.mockResolvedValue({
      sessionId: 's1',
      jobId: 'job-1',
      status: 'queued',
      previewUrl: '/api/preview/s1',
      estimatedTimeSeconds: 8,
      wsStatusUrl: '/ws/processing-status/job-1',
    });
    const { result } = renderHook(() => useImageProcessing('s1'));

    act(() => result.current.updateStackParameter('stretch', 0.8));
    expect(result.current.parameters.stack.stretch).toBe(0.8);
    expect(mocked.processImage).not.toHaveBeenCalled();

    await act(async () => {
      document.dispatchEvent(new Event('pointerup'));
    });

    await waitFor(() => expect(mocked.processImage).toHaveBeenCalledTimes(1));
    expect(mocked.processImage).toHaveBeenCalledWith(
      's1',
      expect.objectContaining({ stack: expect.objectContaining({ stretch: 0.8 }) }),
    );
  });

  it('updateChannelCurve stores points on the field for the given channel and defers the render', async () => {
    mocked.processImage.mockResolvedValue({
      sessionId: 's1',
      jobId: 'job-1',
      status: 'queued',
      previewUrl: '/api/preview/s1',
      estimatedTimeSeconds: 8,
      wsStatusUrl: '/ws/processing-status/job-1',
    });
    const { result } = renderHook(() => useImageProcessing('s1'));

    const points = [
      { x: 0, y: 10 },
      { x: 255, y: 255 },
    ];
    act(() => result.current.updateChannelCurve('red', points));
    expect(result.current.parameters.redCurvePoints).toEqual(points);
    expect(mocked.processImage).not.toHaveBeenCalled();

    await act(async () => {
      document.dispatchEvent(new Event('pointerup'));
    });

    await waitFor(() => expect(mocked.processImage).toHaveBeenCalledTimes(1));
    expect(mocked.processImage).toHaveBeenCalledWith(
      's1',
      expect.objectContaining({ redCurvePoints: points }),
    );
  });

  it('applyGeometry commits a new framing at once', async () => {
    mocked.processImage.mockResolvedValue({
      sessionId: 's1',
      jobId: 'job-1',
      status: 'queued',
      previewUrl: '/api/preview/s1',
      estimatedTimeSeconds: 8,
      wsStatusUrl: '/ws/processing-status/job-1',
    });
    const { result } = renderHook(() => useImageProcessing('s1'));
    const geometry = { ...result.current.parameters.geometry, straighten: 12 };

    await act(async () => {
      result.current.applyGeometry(geometry);
    });

    expect(result.current.parameters.geometry.straighten).toBe(12);
    expect(mocked.processImage).toHaveBeenCalledWith(
      's1',
      expect.objectContaining({ geometry: expect.objectContaining({ straighten: 12 }) }),
    );
  });

  it('resetStack puts the Stack step parameters back to default and renders', async () => {
    mocked.processImage.mockResolvedValue({
      sessionId: 's1',
      jobId: 'job-1',
      status: 'queued',
      previewUrl: '/api/preview/s1',
      estimatedTimeSeconds: 8,
      wsStatusUrl: '/ws/processing-status/job-1',
    });
    const { result } = renderHook(() => useImageProcessing('s1'));
    act(() => result.current.updateStackParameter('stretch', 0.9));

    await act(async () => {
      result.current.resetStack();
    });

    expect(result.current.parameters.stack.stretch).toBe(0.5);
    await waitFor(() =>
      expect(mocked.processImage).toHaveBeenCalledWith(
        's1',
        expect.objectContaining({ stack: expect.objectContaining({ stretch: 0.5 }) }),
      ),
    );
  });

  it('resetCurves clears every tone curve and renders', async () => {
    mocked.processImage.mockResolvedValue({
      sessionId: 's1',
      jobId: 'job-1',
      status: 'queued',
      previewUrl: '/api/preview/s1',
      estimatedTimeSeconds: 8,
      wsStatusUrl: '/ws/processing-status/job-1',
    });
    const { result } = renderHook(() => useImageProcessing('s1'));
    act(() =>
      result.current.updateChannelCurve('rgb', [
        { x: 0, y: 5 },
        { x: 255, y: 250 },
      ]),
    );

    await act(async () => {
      result.current.resetCurves();
    });

    expect(result.current.parameters.curvePoints).toEqual([]);
    expect(result.current.parameters.redCurvePoints).toEqual([]);
    expect(result.current.parameters.greenCurvePoints).toEqual([]);
    expect(result.current.parameters.blueCurvePoints).toEqual([]);
    await waitFor(() => expect(mocked.processImage).toHaveBeenCalled());
  });

  it('resetKeys resets only the given parameters and forgets any slider revert', async () => {
    mocked.processImage.mockResolvedValue({
      sessionId: 's1',
      jobId: 'job-1',
      status: 'queued',
      previewUrl: '/api/preview/s1',
      estimatedTimeSeconds: 8,
      wsStatusUrl: '/ws/processing-status/job-1',
    });
    const { result } = renderHook(() => useImageProcessing('s1'));
    act(() => result.current.updateParameter('contrast', 1.7));
    expect(result.current.sliderRevert).not.toBeNull();

    await act(async () => {
      result.current.resetKeys(['contrast']);
    });

    expect(result.current.parameters.contrast).toBe(1.0);
    expect(result.current.sliderRevert).toBeNull();
    await waitFor(() =>
      expect(mocked.processImage).toHaveBeenCalledWith(
        's1',
        expect.objectContaining({ contrast: 1.0 }),
      ),
    );
  });

  it('forgetSliderRevert is a no-op when nothing is being reverted', async () => {
    mocked.processImage.mockResolvedValue({
      sessionId: 's1',
      jobId: 'job-1',
      status: 'queued',
      previewUrl: '/api/preview/s1',
      estimatedTimeSeconds: 8,
      wsStatusUrl: '/ws/processing-status/job-1',
    });
    const { result } = renderHook(() => useImageProcessing('s1'));

    await act(async () => {
      result.current.resetKeys(['contrast']);
    });

    expect(result.current.sliderRevert).toBeNull();
  });

  it('syncParameters updates state without triggering a render, and cancels a pending debounce', async () => {
    vi.useFakeTimers();
    try {
      const { result } = renderHook(() => useImageProcessing('s1'));
      act(() => result.current.updateParameter('exposure', 0.5)); // schedules the settle-fallback timer

      const synced = { ...result.current.parameters, exposure: 0.9 };
      act(() => result.current.syncParameters(synced));

      expect(result.current.parameters.exposure).toBe(0.9);
      expect(result.current.sliderRevert).toBeNull();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1200);
      });
      expect(mocked.processImage).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('restoreParameters replaces the full snapshot and renders it immediately', async () => {
    mocked.processImage.mockResolvedValue({
      sessionId: 's1',
      jobId: 'job-1',
      status: 'queued',
      previewUrl: '/api/preview/s1',
      estimatedTimeSeconds: 8,
      wsStatusUrl: '/ws/processing-status/job-1',
    });
    const { result } = renderHook(() => useImageProcessing('s1'));
    act(() => result.current.updateParameter('exposure', 0.5));
    expect(result.current.sliderRevert).not.toBeNull();

    const restored = { ...result.current.parameters, exposure: -0.3 };
    await act(async () => {
      result.current.restoreParameters(restored);
    });

    expect(result.current.parameters.exposure).toBe(-0.3);
    expect(result.current.sliderRevert).toBeNull();
    expect(mocked.processImage).toHaveBeenCalledWith(
      's1',
      expect.objectContaining({ exposure: -0.3 }),
    );
  });
});
