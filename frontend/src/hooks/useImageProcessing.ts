import { useCallback, useEffect, useRef, useState } from 'react';

import { useTranslation } from '@/hooks/useTranslation';
import { apiClient } from '@/services/api';
import { errorMessage } from '@/services/apiError';
import { processingStatusClient } from '@/services/ws';
import {
  CURVE_CHANNEL_FIELD,
  DEFAULT_PARAMETERS,
  type CurveChannel,
  type CurvePoint,
  type GeometryParameters,
  type JobStatus,
  type DenoiseEngine,
  type ProcessingParameters,
  type ProcessResponse,
  type SliderParameterKey,
  type StackParameters,
  type StarlessEngine,
} from '@/types';

const DEBOUNCE_MS = 500;

/**
 * Owns the parameter state for a session and pushes debounced updates to the
 * backend, tracking job status over the WebSocket.
 *
 * `previewVersion` increments every time a result finishes; callers append it to
 * the preview URL so the browser re-fetches the (same-URL) processed image.
 */
export function useImageProcessing(sessionId: string) {
  const { t } = useTranslation();
  const [parameters, setParameters] = useState<ProcessingParameters>(DEFAULT_PARAMETERS);
  const [status, setStatus] = useState<JobStatus | 'idle'>('idle');
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState('');
  const [previewVersion, setPreviewVersion] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const wsRef = useRef<ReturnType<typeof processingStatusClient> | null>(null);
  // Only one job is followed at a time. `busy` is set the moment a /process
  // starts and cleared when its job reaches a terminal state; params that arrive
  // while busy are held in `pending` and sent once, on settle. A burst of slider
  // moves therefore becomes at most two backend jobs, never a pile-up of
  // soon-to-be-superseded work fighting over the (un-WAL) SQLite file.
  const busyRef = useRef(false);
  const pendingRef = useRef<ProcessingParameters | null>(null);
  const applyRef = useRef<(next: ProcessingParameters) => void>(() => {});

  /**
   * Follow a processing job over the WebSocket until it finishes, bumping
   * `previewVersion` on completion so the preview refetches. Also handles a job
   * that came back already terminal (PROCESSING_MODE=sync).
   *
   * Used for /process here and, via the returned handle, for jobs kicked off by
   * other endpoints (preset apply, Auto Astro) - without this a queued job
   * (PROCESSING_MODE=queue) would leave the preview on the previous result until
   * the next user action.
   */
  const trackJob = useCallback((response: ProcessResponse) => {
    busyRef.current = true;
    setStatus('processing');
    setProgress(0);
    setCurrentStep('');
    setError(null);
    // Drop the previous job's socket - the backend supersedes its job, so it
    // will never complete and its reconnect loop is just noise.
    wsRef.current?.disconnect();
    wsRef.current = null;

    // Release the slot and send whatever the user changed while this job ran.
    const settle = (): void => {
      busyRef.current = false;
      const queued = pendingRef.current;
      pendingRef.current = null;
      if (queued) {
        applyRef.current(queued);
      }
    };

    if (response.status === 'completed' || response.status === 'failed') {
      // Sync mode: the pipeline already ran (result on disk) - no socket needed.
      if (response.status === 'completed') {
        setStatus('completed');
        setPreviewVersion((version) => version + 1);
      } else {
        setStatus('failed');
        setError('Processing failed');
      }
      settle();
      return;
    }

    const ws = processingStatusClient(response.jobId);
    wsRef.current = ws;
    ws.onStatusUpdate((update) => {
      if (update.status === 'superseded') {
        ws.disconnect();
        settle();
        return;
      }
      setStatus(update.status);
      setProgress(update.progressPercent);
      setCurrentStep(update.currentStep);
      if (update.status === 'completed') {
        setPreviewVersion((version) => version + 1);
        ws.disconnect();
        settle();
      } else if (update.status === 'failed') {
        setError(update.error ?? 'Processing failed');
        ws.disconnect();
        settle();
      }
    });
    ws.connect();
  }, []);

  const applyParameters = useCallback(
    async (next: ProcessingParameters) => {
      // A job is already in flight - remember the latest state and let `settle`
      // send it when that job finishes.
      if (busyRef.current) {
        pendingRef.current = next;
        return;
      }
      busyRef.current = true; // claim the slot before the await
      setStatus('processing');
      setError(null);
      try {
        trackJob(await apiClient.processImage(sessionId, next));
      } catch (err) {
        busyRef.current = false;
        setStatus('failed');
        setError(errorMessage(err, t, 'Processing failed'));
        // A queued edit still deserves a try even if this request errored.
        const queued = pendingRef.current;
        pendingRef.current = null;
        if (queued) {
          void applyParameters(queued);
        }
      }
    },
    [sessionId, t, trackJob],
  );

  applyRef.current = (next: ProcessingParameters) => void applyParameters(next);

  const updateParameter = useCallback(
    (key: SliderParameterKey, value: number) => {
      setParameters((prev) => {
        const next = { ...prev, [key]: value };
        clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => void applyParameters(next), DEBOUNCE_MS);
        return next;
      });
    },
    [applyParameters],
  );

  /** Switch the star-removal / denoise backend. Applied at once, not debounced -
   * it's a deliberate choice and an ML pass is long; there's nothing to coalesce. */
  const updateStarRemovalEngine = useCallback(
    (engine: StarlessEngine) => {
      setParameters((prev) => {
        const next = { ...prev, starRemovalEngine: engine };
        clearTimeout(debounceRef.current);
        void applyParameters(next);
        return next;
      });
    },
    [applyParameters],
  );

  const updateDenoiseEngine = useCallback(
    (engine: DenoiseEngine) => {
      setParameters((prev) => {
        const next = { ...prev, denoiseEngine: engine };
        clearTimeout(debounceRef.current);
        void applyParameters(next);
        return next;
      });
    },
    [applyParameters],
  );

  /** Update one field of the linear post-stack pre-stage (the "Stack" step). */
  const updateStackParameter = useCallback(
    <K extends keyof StackParameters>(key: K, value: StackParameters[K]) => {
      setParameters((prev) => {
        const next = { ...prev, stack: { ...prev.stack, [key]: value } };
        clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => void applyParameters(next), DEBOUNCE_MS);
        return next;
      });
    },
    [applyParameters],
  );

  /** `channel` picks which curve field (see CURVE_CHANNEL_FIELD) gets the new points. */
  const updateChannelCurve = useCallback(
    (channel: CurveChannel, points: CurvePoint[]) => {
      const field = CURVE_CHANNEL_FIELD[channel];
      setParameters((prev) => {
        const next = { ...prev, [field]: points };
        clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => void applyParameters(next), DEBOUNCE_MS);
        return next;
      });
    },
    [applyParameters],
  );

  /** Commit a new framing (crop tool "Done") - processed immediately. */
  const applyGeometry = useCallback(
    (geometry: GeometryParameters) => {
      setParameters((prev) => {
        const next = { ...prev, geometry };
        clearTimeout(debounceRef.current);
        void applyParameters(next);
        return next;
      });
    },
    [applyParameters],
  );

  const resetParameters = useCallback(() => {
    setParameters(DEFAULT_PARAMETERS);
    void applyParameters(DEFAULT_PARAMETERS);
  }, [applyParameters]);

  /** Reset the "Stack" step (stretch / background extraction / colour) to defaults. */
  const resetStack = useCallback(() => {
    setParameters((prev) => {
      const next: ProcessingParameters = { ...prev, stack: { ...DEFAULT_PARAMETERS.stack } };
      clearTimeout(debounceRef.current);
      void applyParameters(next);
      return next;
    });
  }, [applyParameters]);

  /** Reset every tone curve (master + R/G/B) back to identity. */
  const resetCurves = useCallback(() => {
    setParameters((prev) => {
      const next: ProcessingParameters = {
        ...prev,
        curvePoints: [],
        redCurvePoints: [],
        greenCurvePoints: [],
        blueCurvePoints: [],
      };
      clearTimeout(debounceRef.current);
      void applyParameters(next);
      return next;
    });
  }, [applyParameters]);

  /** Reset just the given parameters (e.g. one section's sliders) to default. */
  const resetKeys = useCallback(
    (keys: SliderParameterKey[]) => {
      setParameters((prev) => {
        const next = { ...prev };
        for (const key of keys) {
          next[key] = DEFAULT_PARAMETERS[key];
        }
        clearTimeout(debounceRef.current);
        void applyParameters(next);
        return next;
      });
    },
    [applyParameters],
  );

  /**
   * Sync the sliders to parameters that were already applied elsewhere
   * (e.g. a preset the backend ran) - state only, no processing call.
   */
  const syncParameters = useCallback((next: ProcessingParameters) => {
    clearTimeout(debounceRef.current);
    setParameters(next);
  }, []);

  /**
   * Restore a full parameter snapshot (an edit milestone) - like
   * {@link resetParameters} but for an arbitrary state. Cancels any pending
   * debounced slider update so it can't clobber the restore a moment later.
   */
  const restoreParameters = useCallback(
    (next: ProcessingParameters) => {
      clearTimeout(debounceRef.current);
      setParameters(next);
      void applyParameters(next);
    },
    [applyParameters],
  );

  useEffect(
    () => () => {
      clearTimeout(debounceRef.current);
      wsRef.current?.disconnect();
    },
    [],
  );

  return {
    parameters,
    status,
    progress,
    currentStep,
    previewVersion,
    error,
    updateParameter,
    updateStarRemovalEngine,
    updateDenoiseEngine,
    updateStackParameter,
    updateChannelCurve,
    applyGeometry,
    applyParameters,
    trackJob,
    resetParameters,
    resetStack,
    resetCurves,
    resetKeys,
    syncParameters,
    restoreParameters,
  };
}
