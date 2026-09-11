import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useStackProcessing } from '@/hooks/useStackProcessing';
import { apiClient } from '@/services/api';
import type {
  CalibrationSummary,
  ProcessingStatus,
  StackFrameInfo,
  StackResult,
  StackSession,
  StackSettings,
} from '@/types';

vi.mock('@/services/api', () => ({
  apiClient: {
    initiateStack: vi.fn(),
    uploadStackFrames: vi.fn(),
    getStack: vi.fn(),
    excludeStackFrame: vi.fn(),
    uploadCalibrationFrames: vi.fn(),
    clearCalibration: vi.fn(),
    processStack: vi.fn(),
  },
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
  stackStatusClient: vi.fn(() => new FakeWs()),
}));

const mockedApi = vi.mocked(apiClient);

const EMPTY_CALIBRATION: CalibrationSummary = {
  frames: { dark: 0, flat: 0, bias: 0, darkFlat: 0 },
  cosmeticCorrection: true,
};

const SETTINGS: StackSettings = {
  registrationTransform: 'similarity',
  combinationMethod: 'average',
  rejectionAlgo: 'sigma',
  weighting: 'quality',
  cosmeticCorrection: true,
  qualityFilter: 'moderate',
  postProcess: true,
  drizzleFactor: 1,
};

function frame(index: number, overrides: Partial<StackFrameInfo> = {}): StackFrameInfo {
  return { index, thumbUrl: `/thumb/${index}`, excluded: false, quality: null, ...overrides };
}

function stackResult(overrides: Partial<StackResult> = {}): StackResult {
  return {
    stackId: 's-1',
    status: 'collecting',
    jobId: null,
    wsStatusUrl: null,
    sessionId: null,
    stackedImageUrl: null,
    statistics: null,
    frames: [],
    calibration: null,
    error: null,
    ...overrides,
  };
}

function session(overrides: Partial<StackSession> = {}): StackSession {
  return { stackId: 's-1', status: 'collecting', frameCount: 2, receivedFrames: 0, ...overrides };
}

function statusEvent(overrides: Partial<ProcessingStatus>): ProcessingStatus {
  return {
    jobId: 'job-1',
    status: 'processing',
    progressPercent: 0,
    currentStep: '',
    message: '',
    ...overrides,
  } as ProcessingStatus;
}

describe('useStackProcessing', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    FakeWs.last = null;
  });

  describe('addFiles / removePending', () => {
    it('adds files to pending and removePending removes them', () => {
      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      const f1 = new File(['a'], 'a.fits');
      const f2 = new File(['b'], 'b.fits');

      act(() => result.current.addFiles([f1, f2]));
      expect(result.current.pending).toHaveLength(2);
      expect(result.current.pending.map((p) => p.name)).toEqual(['a.fits', 'b.fits']);
      expect(result.current.error).toBeNull();

      const idToRemove = result.current.pending[0].id;
      act(() => result.current.removePending(idToRemove));
      expect(result.current.pending).toHaveLength(1);
      expect(result.current.pending[0].name).toBe('b.fits');
    });

    it('rejects adding files that would push the total over maxFrames', () => {
      const { result } = renderHook(() => useStackProcessing(SETTINGS, 2));

      act(() => result.current.addFiles([new File(['a'], 'a.fits')]));
      expect(result.current.pending).toHaveLength(1);

      act(() =>
        result.current.addFiles([new File(['b'], 'b.fits'), new File(['c'], 'c.fits')]),
      );
      expect(result.current.pending).toHaveLength(1); // unchanged
      expect(result.current.error).toBe(
        '3 frames selected - this instance allows at most 2 per stack (raise it in Settings).',
      );
    });
  });

  describe('uploadFrames', () => {
    it('refuses when there are too few frames total', async () => {
      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));

      await act(async () => {
        await result.current.uploadFrames();
      });

      expect(result.current.error).toBe('Add at least 2 frames to stack.');
      expect(result.current.phase).toBe('collecting');
      expect(mockedApi.initiateStack).not.toHaveBeenCalled();
    });

    it('uploads pending frames in batches, then loads the stack and moves to reviewing', async () => {
      mockedApi.initiateStack.mockResolvedValue(session({ stackId: 'stack-1' }));
      mockedApi.uploadStackFrames.mockResolvedValue(session({ stackId: 'stack-1' }));
      mockedApi.getStack.mockResolvedValue(
        stackResult({
          stackId: 'stack-1',
          frames: [frame(0), frame(1), frame(2)],
          calibration: { frames: { dark: 1, flat: 0, bias: 0, darkFlat: 0 }, cosmeticCorrection: false },
        }),
      );

      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      const files = Array.from({ length: 25 }, (_, i) => new File([`f${i}`], `f${i}.fits`));
      act(() => result.current.addFiles(files));

      await act(async () => {
        await result.current.uploadFrames();
      });

      expect(mockedApi.initiateStack).toHaveBeenCalledTimes(1);
      expect(mockedApi.initiateStack).toHaveBeenCalledWith(25, SETTINGS);
      expect(mockedApi.uploadStackFrames).toHaveBeenCalledTimes(2); // batched: 20 + 5
      expect(mockedApi.uploadStackFrames).toHaveBeenNthCalledWith(1, 'stack-1', 0, expect.any(Array));
      expect(mockedApi.uploadStackFrames).toHaveBeenNthCalledWith(
        2,
        'stack-1',
        20,
        expect.any(Array),
      );
      expect(result.current.uploaded).toHaveLength(3);
      expect(result.current.calibration.frames.dark).toBe(1);
      expect(result.current.pending).toHaveLength(0);
      expect(result.current.selected).toBe(0);
      expect(result.current.phase).toBe('reviewing');
    });

    it('selects nothing when the uploaded stack comes back with no frames', async () => {
      mockedApi.initiateStack.mockResolvedValue(session());
      mockedApi.uploadStackFrames.mockResolvedValue(session());
      mockedApi.getStack.mockResolvedValue(stackResult({ frames: [], calibration: null }));

      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      act(() =>
        result.current.addFiles([new File(['a'], 'a.fits'), new File(['b'], 'b.fits')]),
      );

      await act(async () => {
        await result.current.uploadFrames();
      });

      expect(result.current.selected).toBeNull();
      expect(result.current.phase).toBe('reviewing');
    });

    it('surfaces an Error message and falls back to collecting when nothing was uploaded yet', async () => {
      mockedApi.initiateStack.mockRejectedValue(new Error('network down'));

      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      act(() =>
        result.current.addFiles([new File(['a'], 'a.fits'), new File(['b'], 'b.fits')]),
      );

      await act(async () => {
        await result.current.uploadFrames();
      });

      expect(result.current.error).toBe('network down');
      expect(result.current.phase).toBe('collecting');
    });

    it('reuses the existing stack id and stays in reviewing on a later failed upload', async () => {
      mockedApi.initiateStack.mockResolvedValue(session({ stackId: 'stack-1' }));
      mockedApi.uploadStackFrames.mockResolvedValue(session({ stackId: 'stack-1' }));
      mockedApi.getStack.mockResolvedValueOnce(
        stackResult({ stackId: 'stack-1', frames: [frame(0), frame(1)] }),
      );

      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      act(() =>
        result.current.addFiles([new File(['a'], 'a.fits'), new File(['b'], 'b.fits')]),
      );
      await act(async () => {
        await result.current.uploadFrames();
      });
      expect(result.current.phase).toBe('reviewing');

      // A second batch fails with a non-Error rejection - falls back to the
      // translated message, and stays in reviewing since frames already exist.
      mockedApi.uploadStackFrames.mockRejectedValueOnce('boom');
      act(() => result.current.addFiles([new File(['c'], 'c.fits')]));
      await act(async () => {
        await result.current.uploadFrames();
      });

      expect(mockedApi.initiateStack).toHaveBeenCalledTimes(1); // reused, not re-initiated
      expect(result.current.error).toBe('Stacking failed.');
      expect(result.current.phase).toBe('reviewing');
    });
  });

  describe('calibration frames', () => {
    it('addCalibrationFiles is a no-op for an empty file list', async () => {
      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));

      await act(async () => {
        await result.current.addCalibrationFiles('dark', []);
      });

      expect(mockedApi.initiateStack).not.toHaveBeenCalled();
      expect(result.current.calibration).toEqual(EMPTY_CALIBRATION);
    });

    it('ensures a stack, uploads calibration frames, and stores the summary', async () => {
      mockedApi.initiateStack.mockResolvedValue(session({ stackId: 'stack-9' }));
      mockedApi.uploadCalibrationFrames.mockResolvedValue({
        frames: { dark: 3, flat: 0, bias: 0, darkFlat: 0 },
        cosmeticCorrection: true,
      });

      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      await act(async () => {
        await result.current.addCalibrationFiles('dark', [new File(['d'], 'd.fits')]);
      });

      expect(mockedApi.initiateStack).toHaveBeenCalledTimes(1);
      expect(mockedApi.initiateStack).toHaveBeenCalledWith(2, SETTINGS);
      expect(mockedApi.uploadCalibrationFrames).toHaveBeenCalledWith(
        'stack-9',
        'dark',
        expect.any(Array),
      );
      expect(result.current.calibration.frames.dark).toBe(3);
    });

    it('surfaces an Error message from a failed calibration upload', async () => {
      mockedApi.initiateStack.mockResolvedValue(session({ stackId: 'stack-9' }));
      mockedApi.uploadCalibrationFrames.mockRejectedValue(new Error('upload failed'));

      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      await act(async () => {
        await result.current.addCalibrationFiles('dark', [new File(['d'], 'd.fits')]);
      });

      expect(result.current.error).toBe('upload failed');
    });

    it('falls back to a translated message for a non-Error calibration rejection', async () => {
      mockedApi.initiateStack.mockResolvedValue(session({ stackId: 'stack-9' }));
      mockedApi.uploadCalibrationFrames.mockRejectedValue('nope');

      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      await act(async () => {
        await result.current.addCalibrationFiles('dark', [new File(['d'], 'd.fits')]);
      });

      expect(result.current.error).toBe('Stacking failed.');
    });

    it('clearCalibrationKind is a no-op before a stack exists', async () => {
      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));

      await act(async () => {
        await result.current.clearCalibrationKind('dark');
      });

      expect(mockedApi.clearCalibration).not.toHaveBeenCalled();
    });

    it('clears a calibration kind once a stack exists', async () => {
      mockedApi.initiateStack.mockResolvedValue(session({ stackId: 'stack-5' }));
      mockedApi.uploadCalibrationFrames.mockResolvedValue({
        frames: { dark: 2, flat: 0, bias: 0, darkFlat: 0 },
        cosmeticCorrection: true,
      });
      mockedApi.clearCalibration.mockResolvedValue({
        frames: { dark: 0, flat: 0, bias: 0, darkFlat: 0 },
        cosmeticCorrection: true,
      });

      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      await act(async () => {
        await result.current.addCalibrationFiles('dark', [new File(['d'], 'd.fits')]);
      });
      expect(result.current.calibration.frames.dark).toBe(2);

      await act(async () => {
        await result.current.clearCalibrationKind('dark');
      });

      expect(mockedApi.clearCalibration).toHaveBeenCalledWith('stack-5', 'dark');
      expect(result.current.calibration.frames.dark).toBe(0);
    });

    it('silently keeps the current count when clearing a calibration kind fails', async () => {
      mockedApi.initiateStack.mockResolvedValue(session({ stackId: 'stack-5' }));
      mockedApi.uploadCalibrationFrames.mockResolvedValue({
        frames: { dark: 2, flat: 0, bias: 0, darkFlat: 0 },
        cosmeticCorrection: true,
      });
      mockedApi.clearCalibration.mockRejectedValue(new Error('nope'));

      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      await act(async () => {
        await result.current.addCalibrationFiles('dark', [new File(['d'], 'd.fits')]);
      });

      await act(async () => {
        await result.current.clearCalibrationKind('dark');
      });

      expect(result.current.calibration.frames.dark).toBe(2); // unchanged
      expect(result.current.error).toBeNull(); // failure is swallowed
    });
  });

  describe('toggleExclude', () => {
    it('is a no-op before a stack exists', async () => {
      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));

      await act(async () => {
        await result.current.toggleExclude(0, true);
      });

      expect(mockedApi.excludeStackFrame).not.toHaveBeenCalled();
      expect(result.current.uploaded).toEqual([]);
    });

    it('optimistically flips the frame and keeps it on success', async () => {
      mockedApi.excludeStackFrame.mockResolvedValue(frame(1, { excluded: true }));
      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      act(() =>
        result.current.attachToStack(
          stackResult({ stackId: 'stack-2', status: 'reviewing', frames: [frame(0), frame(1)] }),
        ),
      );
      expect(result.current.uploaded[1].excluded).toBe(false);

      await act(async () => {
        await result.current.toggleExclude(1, true);
      });

      expect(result.current.uploaded[1].excluded).toBe(true);
      expect(mockedApi.excludeStackFrame).toHaveBeenCalledWith('stack-2', 1, true);
    });

    it('reverts the optimistic flip on failure', async () => {
      mockedApi.excludeStackFrame.mockRejectedValue(new Error('nope'));
      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      act(() =>
        result.current.attachToStack(
          stackResult({ stackId: 'stack-2', status: 'reviewing', frames: [frame(0), frame(1)] }),
        ),
      );

      await act(async () => {
        await result.current.toggleExclude(1, true);
      });

      expect(result.current.uploaded[1].excluded).toBe(false); // reverted
    });
  });

  describe('stack processing', () => {
    it('refuses when there is no stack yet', async () => {
      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));

      await act(async () => {
        await result.current.stack();
      });

      expect(result.current.error).toBe('Add at least 2 frames to stack.');
      expect(mockedApi.processStack).not.toHaveBeenCalled();
    });

    it('refuses when fewer than 2 active frames remain', async () => {
      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      act(() =>
        result.current.attachToStack(
          stackResult({
            stackId: 's',
            status: 'reviewing',
            frames: [frame(0, { excluded: true }), frame(1, { excluded: true })],
          }),
        ),
      );

      await act(async () => {
        await result.current.stack();
      });

      expect(result.current.error).toBe('Add at least 2 frames to stack.');
      expect(mockedApi.processStack).not.toHaveBeenCalled();
    });

    it('follows a queued job over the WebSocket to completion', async () => {
      mockedApi.processStack.mockResolvedValue(
        stackResult({ stackId: 's1', status: 'processing', jobId: 'job-1', frames: [] }),
      );
      mockedApi.getStack.mockResolvedValue(
        stackResult({
          stackId: 's1',
          status: 'completed',
          frames: [frame(0), frame(1)],
          calibration: { frames: { dark: 0, flat: 0, bias: 0, darkFlat: 0 }, cosmeticCorrection: true },
        }),
      );

      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      act(() =>
        result.current.attachToStack(
          stackResult({ stackId: 's1', status: 'reviewing', frames: [frame(0), frame(1)] }),
        ),
      );

      await act(async () => {
        await result.current.stack();
      });
      expect(result.current.phase).toBe('processing');
      expect(FakeWs.last?.connected).toBe(true);

      act(() =>
        FakeWs.last?.emit(
          statusEvent({ status: 'processing', progressPercent: 55, currentStep: 'registration', detail: '10/20' }),
        ),
      );
      expect(result.current.progress).toEqual({ percent: 55, step: 'registration', detail: '10/20' });
      expect(result.current.phase).toBe('processing'); // not yet terminal

      await act(async () => {
        FakeWs.last?.emit(statusEvent({ status: 'completed', progressPercent: 100, currentStep: 'done' }));
      });

      await waitFor(() => expect(result.current.phase).toBe('done'));
      expect(result.current.result?.status).toBe('completed');
      expect(result.current.uploaded).toHaveLength(2);
      expect(FakeWs.last?.disconnected).toBe(true);
    });

    it('does not touch calibration when the final response has none', async () => {
      mockedApi.processStack.mockResolvedValue(
        stackResult({ stackId: 's6', status: 'processing', jobId: 'job-6', frames: [] }),
      );
      mockedApi.getStack.mockResolvedValue(
        stackResult({ stackId: 's6', status: 'completed', frames: [frame(0)], calibration: null }),
      );

      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      act(() =>
        result.current.attachToStack(
          stackResult({ stackId: 's6', status: 'reviewing', frames: [frame(0), frame(1)] }),
        ),
      );
      await act(async () => {
        await result.current.stack();
      });
      await act(async () => {
        FakeWs.last?.emit(statusEvent({ status: 'completed', progressPercent: 100, currentStep: 'done' }));
      });

      await waitFor(() => expect(result.current.phase).toBe('done'));
      expect(result.current.calibration).toEqual(EMPTY_CALIBRATION);
    });

    it('completes at once when the backend already finished (no jobId)', async () => {
      mockedApi.processStack.mockResolvedValue(
        stackResult({ stackId: 's2', status: 'completed', jobId: null, frames: [frame(0), frame(1)] }),
      );

      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      act(() =>
        result.current.attachToStack(
          stackResult({ stackId: 's2', status: 'reviewing', frames: [frame(0), frame(1)] }),
        ),
      );

      await act(async () => {
        await result.current.stack();
      });

      expect(result.current.phase).toBe('done');
      expect(result.current.progress).toEqual({ percent: 100, step: 'done' });
      expect(mockedApi.getStack).not.toHaveBeenCalled(); // follow() never engaged
    });

    it('completes at once when a jobId is present but the status is already terminal', async () => {
      mockedApi.processStack.mockResolvedValue(
        stackResult({
          stackId: 's3',
          status: 'failed',
          jobId: 'job-x',
          frames: [frame(0), frame(1)],
          error: 'oops',
        }),
      );

      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      act(() =>
        result.current.attachToStack(
          stackResult({ stackId: 's3', status: 'reviewing', frames: [frame(0), frame(1)] }),
        ),
      );

      await act(async () => {
        await result.current.stack();
      });

      expect(result.current.phase).toBe('done');
      expect(mockedApi.getStack).not.toHaveBeenCalled();
    });

    it('surfaces an error and returns to reviewing when the request fails', async () => {
      mockedApi.processStack.mockRejectedValue(new Error('boom'));

      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      act(() =>
        result.current.attachToStack(
          stackResult({ stackId: 's4', status: 'reviewing', frames: [frame(0), frame(1)] }),
        ),
      );

      await act(async () => {
        await result.current.stack();
      });

      expect(result.current.error).toBe('boom');
      expect(result.current.phase).toBe('reviewing');
    });

    it('still reaches done when the final getStack fetch fails', async () => {
      mockedApi.processStack.mockResolvedValue(
        stackResult({ stackId: 's5', status: 'processing', jobId: 'job-5', frames: [] }),
      );
      mockedApi.getStack.mockRejectedValue(new Error('fetch failed'));

      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      act(() =>
        result.current.attachToStack(
          stackResult({ stackId: 's5', status: 'reviewing', frames: [frame(0), frame(1)] }),
        ),
      );
      await act(async () => {
        await result.current.stack();
      });

      await act(async () => {
        FakeWs.last?.emit(statusEvent({ status: 'failed', progressPercent: 0, currentStep: '' }));
      });

      await waitFor(() => expect(result.current.phase).toBe('done'));
      // getStack's rejection is swallowed (only setPhase('done') runs in the
      // .catch) - result keeps the stale value stack() set from processStack,
      // it is never reset to null.
      expect(result.current.result?.status).toBe('processing');
    });
  });

  describe('attachToStack / pollUntilDone', () => {
    it('opens a completed snapshot directly', () => {
      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      act(() =>
        result.current.attachToStack(
          stackResult({ stackId: 's7', status: 'completed', frames: [frame(0), frame(1)] }),
        ),
      );

      expect(result.current.phase).toBe('done');
      expect(result.current.progress).toEqual({ percent: 100, step: 'done' });
      expect(result.current.uploaded).toHaveLength(2);
      expect(result.current.result?.status).toBe('completed');
    });

    it('opens a reviewing snapshot as reviewing', () => {
      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      act(() =>
        result.current.attachToStack(
          stackResult({ stackId: 's8', status: 'reviewing', frames: [frame(0)] }),
        ),
      );

      expect(result.current.phase).toBe('reviewing');
    });

    it('opens a processing snapshot and polls until it completes', async () => {
      vi.useFakeTimers();
      try {
        mockedApi.getStack.mockResolvedValueOnce(
          stackResult({ stackId: 's9', status: 'processing', frames: [] }),
        );
        mockedApi.getStack.mockResolvedValueOnce(
          stackResult({
            stackId: 's9',
            status: 'completed',
            frames: [frame(0), frame(1)],
            calibration: { frames: { dark: 1, flat: 0, bias: 0, darkFlat: 0 }, cosmeticCorrection: true },
          }),
        );

        const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
        act(() =>
          result.current.attachToStack(
            stackResult({ stackId: 's9', status: 'processing', frames: [] }),
          ),
        );
        expect(result.current.phase).toBe('processing');
        expect(result.current.progress).toEqual({ percent: 0, step: 'registration' });

        await act(async () => {
          await vi.advanceTimersByTimeAsync(3000);
        });
        expect(result.current.phase).toBe('processing'); // first poll: still running

        await act(async () => {
          await vi.advanceTimersByTimeAsync(3000);
        });
        expect(result.current.phase).toBe('done');
        expect(result.current.calibration.frames.dark).toBe(1);
      } finally {
        vi.useRealTimers();
      }
    });

    it('moves to reviewing (not done) when a polled stack failed', async () => {
      vi.useFakeTimers();
      try {
        mockedApi.getStack.mockResolvedValueOnce(
          stackResult({ stackId: 's10', status: 'failed', frames: [frame(0)], error: 'boom' }),
        );

        const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
        act(() =>
          result.current.attachToStack(
            stackResult({ stackId: 's10', status: 'processing', frames: [] }),
          ),
        );

        await act(async () => {
          await vi.advanceTimersByTimeAsync(3000);
        });
        expect(result.current.phase).toBe('reviewing');
      } finally {
        vi.useRealTimers();
      }
    });

    it('ignores a failed poll fetch and keeps polling', async () => {
      vi.useFakeTimers();
      try {
        mockedApi.getStack.mockRejectedValueOnce(new Error('network blip'));
        mockedApi.getStack.mockResolvedValueOnce(
          stackResult({ stackId: 's11', status: 'completed', frames: [frame(0), frame(1)] }),
        );

        const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
        act(() =>
          result.current.attachToStack(
            stackResult({ stackId: 's11', status: 'processing', frames: [] }),
          ),
        );

        await act(async () => {
          await vi.advanceTimersByTimeAsync(3000);
        });
        expect(result.current.phase).toBe('processing');

        await act(async () => {
          await vi.advanceTimersByTimeAsync(3000);
        });
        expect(result.current.phase).toBe('done');
      } finally {
        vi.useRealTimers();
      }
    });

    it('tears down an in-progress WebSocket follow before opening a new snapshot', async () => {
      mockedApi.processStack.mockResolvedValue(
        stackResult({ stackId: 's14', status: 'processing', jobId: 'job-14', frames: [] }),
      );

      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      act(() =>
        result.current.attachToStack(
          stackResult({ stackId: 's14', status: 'reviewing', frames: [frame(0), frame(1)] }),
        ),
      );
      await act(async () => {
        await result.current.stack();
      });
      const ws = FakeWs.last;
      expect(ws?.connected).toBe(true);

      act(() =>
        result.current.attachToStack(
          stackResult({ stackId: 's15', status: 'reviewing', frames: [frame(0)] }),
        ),
      );

      expect(ws?.disconnected).toBe(true);
      expect(result.current.phase).toBe('reviewing');
    });

    it('clears a previous poll interval before starting a new one', () => {
      vi.useFakeTimers();
      try {
        mockedApi.getStack.mockResolvedValue(
          stackResult({ stackId: 's12', status: 'processing', frames: [] }),
        );

        const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
        act(() =>
          result.current.attachToStack(
            stackResult({ stackId: 's12', status: 'processing', frames: [] }),
          ),
        );
        expect(result.current.phase).toBe('processing');

        act(() =>
          result.current.attachToStack(
            stackResult({ stackId: 's13', status: 'reviewing', frames: [frame(0)] }),
          ),
        );
        expect(result.current.phase).toBe('reviewing');
      } finally {
        vi.useRealTimers();
      }
    });
  });

  describe('select / activeCount', () => {
    it('toggles the selected frame index', () => {
      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));

      act(() => result.current.select(2));
      expect(result.current.selected).toBe(2);
      act(() => result.current.select(2));
      expect(result.current.selected).toBeNull();
      act(() => result.current.select(5));
      expect(result.current.selected).toBe(5);
    });

    it('counts only non-excluded uploaded frames', () => {
      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      act(() =>
        result.current.attachToStack(
          stackResult({
            stackId: 's18',
            status: 'reviewing',
            frames: [frame(0), frame(1, { excluded: true }), frame(2)],
          }),
        ),
      );

      expect(result.current.activeCount).toBe(2);
    });
  });

  describe('reset', () => {
    it('clears everything, including a live socket', async () => {
      mockedApi.processStack.mockResolvedValue(
        stackResult({ stackId: 's16', status: 'processing', jobId: 'job-16', frames: [] }),
      );

      const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
      act(() =>
        result.current.attachToStack(
          stackResult({ stackId: 's16', status: 'reviewing', frames: [frame(0), frame(1)] }),
        ),
      );
      await act(async () => {
        await result.current.stack();
      });
      const ws = FakeWs.last;

      act(() => result.current.reset());

      expect(ws?.disconnected).toBe(true);
      expect(result.current.phase).toBe('collecting');
      expect(result.current.pending).toEqual([]);
      expect(result.current.uploaded).toEqual([]);
      expect(result.current.selected).toBeNull();
      expect(result.current.result).toBeNull();
      expect(result.current.progress).toEqual({ percent: 0, step: '' });
      expect(result.current.error).toBeNull();
      expect(result.current.calibration).toEqual(EMPTY_CALIBRATION);
    });

    it('clears an active poll interval too', async () => {
      vi.useFakeTimers();
      try {
        mockedApi.getStack.mockResolvedValue(
          stackResult({ stackId: 's17', status: 'processing', frames: [] }),
        );

        const { result } = renderHook(() => useStackProcessing(SETTINGS, 50));
        act(() =>
          result.current.attachToStack(
            stackResult({ stackId: 's17', status: 'processing', frames: [] }),
          ),
        );
        expect(result.current.phase).toBe('processing');

        act(() => result.current.reset());
        expect(result.current.phase).toBe('collecting');

        // The interval was cleared - advancing timers must not resurrect state.
        await act(async () => {
          await vi.advanceTimersByTimeAsync(3000);
        });
        expect(result.current.phase).toBe('collecting');
      } finally {
        vi.useRealTimers();
      }
    });
  });

  describe('unmount cleanup', () => {
    it('disconnects an active WebSocket on unmount', async () => {
      mockedApi.processStack.mockResolvedValue(
        stackResult({ stackId: 's20', status: 'processing', jobId: 'job-20', frames: [] }),
      );

      const { result, unmount } = renderHook(() => useStackProcessing(SETTINGS, 50));
      act(() =>
        result.current.attachToStack(
          stackResult({ stackId: 's20', status: 'reviewing', frames: [frame(0), frame(1)] }),
        ),
      );
      await act(async () => {
        await result.current.stack();
      });
      const ws = FakeWs.last;

      unmount();
      expect(ws?.disconnected).toBe(true);
    });

    it('clears an active poll interval on unmount without throwing', async () => {
      vi.useFakeTimers();
      try {
        mockedApi.getStack.mockResolvedValue(
          stackResult({ stackId: 's19', status: 'processing', frames: [] }),
        );

        const { result, unmount } = renderHook(() => useStackProcessing(SETTINGS, 50));
        act(() =>
          result.current.attachToStack(
            stackResult({ stackId: 's19', status: 'processing', frames: [] }),
          ),
        );

        unmount();

        await act(async () => {
          await vi.advanceTimersByTimeAsync(3000);
        });
      } finally {
        vi.useRealTimers();
      }
    });
  });
});
