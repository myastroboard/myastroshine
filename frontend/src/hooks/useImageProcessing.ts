import { useCallback, useEffect, useRef, useState } from 'react';

import { apiClient } from '@/services/api';
import { processingStatusClient } from '@/services/ws';
import { DEFAULT_PARAMETERS, type JobStatus, type ProcessingParameters } from '@/types';

const DEBOUNCE_MS = 500;

/**
 * Owns the parameter state for a session and pushes debounced updates to the
 * backend, tracking job status over the WebSocket.
 */
export function useImageProcessing(sessionId: string) {
  const [parameters, setParameters] = useState<ProcessingParameters>(DEFAULT_PARAMETERS);
  const [status, setStatus] = useState<JobStatus | 'idle'>('idle');
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const applyParameters = useCallback(
    async (next: ProcessingParameters) => {
      setStatus('processing');
      setError(null);
      try {
        const response = await apiClient.processImage(sessionId, next);
        const ws = processingStatusClient(response.jobId);
        ws.onStatusUpdate((update) => {
          setStatus(update.status);
          setProgress(update.progressPercent);
          if (update.status === 'completed' || update.status === 'failed') {
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
    (key: keyof ProcessingParameters, value: number) => {
      setParameters((prev) => {
        const next = { ...prev, [key]: value };
        clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => void applyParameters(next), DEBOUNCE_MS);
        return next;
      });
    },
    [applyParameters],
  );

  const resetParameters = useCallback(() => {
    setParameters(DEFAULT_PARAMETERS);
    void applyParameters(DEFAULT_PARAMETERS);
  }, [applyParameters]);

  useEffect(() => () => clearTimeout(debounceRef.current), []);

  return { parameters, status, progress, error, updateParameter, applyParameters, resetParameters };
}
