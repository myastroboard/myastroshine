import { useCallback, useEffect, useRef, useState } from 'react';

import type { StackFrame } from '@/components/stacking/StackUploadZone';
import { apiClient } from '@/services/api';
import { type WebSocketClient, stackStatusClient } from '@/services/ws';
import type { StackResult, StackSettings } from '@/types';

const TERMINAL = new Set(['completed', 'failed']);

export interface StackProgressState {
  percent: number;
  step: string;
}

/**
 * Drives the stacking workflow (v1.1): collect frames, upload them, run the
 * process step, then follow progress over the WebSocket until the stack is
 * done (in `PROCESSING_MODE=sync` the result is already terminal and the
 * socket just replays the final state).
 */
export function useStackProcessing(settings: StackSettings) {
  const [frames, setFrames] = useState<StackFrame[]>([]);
  const [result, setResult] = useState<StackResult | null>(null);
  const [phase, setPhase] = useState<'idle' | 'uploading' | 'processing' | 'done'>('idle');
  const [progress, setProgress] = useState<StackProgressState>({ percent: 0, step: '' });
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocketClient | null>(null);

  useEffect(() => () => wsRef.current?.disconnect(), []);

  const setFrameStatus = useCallback((index: number, status: StackFrame['status']) => {
    setFrames((prev) =>
      prev.map((frame) => (frame.index === index ? { ...frame, status } : frame)),
    );
  }, []);

  const addFiles = useCallback((files: File[]) => {
    setFrames((prev) => [
      ...prev,
      ...files.map((file, offset) => ({
        index: prev.length + offset,
        name: file.name,
        sizeBytes: file.size,
        status: 'queued' as const,
        progress: 0,
        file,
      })),
    ]);
  }, []);

  const follow = useCallback((stackId: string, jobId: string) => {
    wsRef.current?.disconnect();
    const ws = stackStatusClient(jobId);
    wsRef.current = ws;
    ws.onStatusUpdate((status) => {
      setProgress({ percent: status.progressPercent, step: status.currentStep });
      if (TERMINAL.has(status.status)) {
        ws.disconnect();
        wsRef.current = null;
        apiClient
          .getStack(stackId)
          .then((final) => {
            setResult(final);
            setPhase('done');
          })
          .catch(() => setPhase('done'));
      }
    });
    ws.connect();
  }, []);

  const run = useCallback(async () => {
    if (frames.length < 2) {
      setError('At least 2 frames are required to stack');
      return;
    }
    setError(null);
    setResult(null);
    setProgress({ percent: 0, step: '' });
    setPhase('uploading');
    try {
      const session = await apiClient.initiateStack(frames.length, settings);
      for (const frame of frames) {
        setFrameStatus(frame.index, 'uploading');
        await apiClient.uploadStackFrame(session.stackId, frame.index, frame.file);
        setFrameStatus(frame.index, 'done');
      }
      setPhase('processing');
      const started = await apiClient.processStack(session.stackId);
      setResult(started);
      if (started.jobId && !TERMINAL.has(started.status)) {
        follow(session.stackId, started.jobId);
      } else {
        setProgress({ percent: 100, step: 'done' });
        setPhase('done');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Stacking failed');
      setPhase('idle');
    }
  }, [frames, settings, follow, setFrameStatus]);

  return { frames, addFiles, run, result, phase, progress, error };
}
