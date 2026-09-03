import { useCallback, useState } from 'react';

import { apiClient } from '@/services/api';
import { stackStatusClient } from '@/services/ws';
import type { StackResult, StackSettings } from '@/types';
import type { StackFrame } from '@/components/stacking/StackUploadZone';

/**
 * Drives the stacking workflow (v1.1+): collect frames, upload them, start
 * processing, and track progress over the WebSocket.
 */
export function useStackProcessing(settings: StackSettings) {
  const [frames, setFrames] = useState<StackFrame[]>([]);
  const [result, setResult] = useState<StackResult | null>(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const addFiles = useCallback((files: File[]) => {
    setFrames((prev) => [
      ...prev,
      ...files.map((file, offset) => ({
        index: prev.length + offset,
        name: file.name,
        sizeBytes: file.size,
        status: 'queued' as const,
        progress: 0,
      })),
    ]);
  }, []);

  const process = useCallback(async () => {
    setError(null);
    try {
      const { stackSessionId } = await apiClient.initiateStack(frames.length, settings);
      const ws = stackStatusClient(stackSessionId);
      ws.onStatusUpdate((update) => {
        setProgress(update.progressPercent);
        if (update.status === 'completed') {
          void apiClient.getStack(stackSessionId).then(setResult);
          ws.disconnect();
        }
      });
      ws.connect();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Stacking failed');
    }
  }, [frames.length, settings]);

  return { frames, addFiles, process, result, progress, error };
}
