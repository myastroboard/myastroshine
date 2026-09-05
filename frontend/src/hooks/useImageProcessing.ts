import { useCallback, useEffect, useRef, useState } from 'react';

import { apiClient } from '@/services/api';
import { processingStatusClient } from '@/services/ws';
import {
  DEFAULT_PARAMETERS,
  type GeometryParameters,
  type JobStatus,
  type ProcessingParameters,
  type SliderParameterKey,
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
  const [parameters, setParameters] = useState<ProcessingParameters>(DEFAULT_PARAMETERS);
  const [status, setStatus] = useState<JobStatus | 'idle'>('idle');
  const [progress, setProgress] = useState(0);
  const [previewVersion, setPreviewVersion] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const applyParameters = useCallback(
    async (next: ProcessingParameters) => {
      setStatus('processing');
      setError(null);
      try {
        const response = await apiClient.processImage(sessionId, next);
        if (response.status === 'completed') {
          setStatus('completed');
          setPreviewVersion((version) => version + 1);
        }
        const ws = processingStatusClient(response.jobId);
        ws.onStatusUpdate((update) => {
          setStatus(update.status);
          setProgress(update.progressPercent);
          if (update.status === 'completed') {
            setPreviewVersion((version) => version + 1);
            ws.disconnect();
          } else if (update.status === 'failed') {
            setError(update.error ?? 'Processing failed');
            ws.disconnect();
          }
        });
        ws.connect();
      } catch (err) {
        setStatus('failed');
        setError(err instanceof Error ? err.message : 'Processing failed');
      }
    },
    [sessionId],
  );

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

  useEffect(() => () => clearTimeout(debounceRef.current), []);

  return {
    parameters,
    status,
    progress,
    previewVersion,
    error,
    updateParameter,
    applyGeometry,
    applyParameters,
    resetParameters,
    resetKeys,
    syncParameters,
  };
}
