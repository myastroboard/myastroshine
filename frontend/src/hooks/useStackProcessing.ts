import { useCallback, useEffect, useRef, useState } from 'react';

import { useTranslation } from '@/hooks/useTranslation';
import { apiClient } from '@/services/api';
import { type WebSocketClient, stackStatusClient } from '@/services/ws';
import type {
  CalibrationKind,
  CalibrationSummary,
  StackFrameInfo,
  StackResult,
  StackSettings,
} from '@/types';

const TERMINAL = new Set(['completed', 'failed']);
const MIN_FRAMES = 2;
const MIB = 1024 * 1024;
/** Share of a batch's progress given to sending it; the rest is the server
 * reading the frames, which only the response reports. */
const SEND_SHARE = 0.85;
/** Aim for at least this many requests: the server reads a request's frames
 * before answering, so the bar can only move between requests - a few big ones
 * would leave it frozen for seconds at a time. */
const MIN_UPLOAD_REQUESTS = 8;
const UPLOAD_BATCH_SIZE = 20; // files per request - keeps a 1000-frame night to ~50 requests; backend UPLOAD_BATCH_MAX_FILES

const EMPTY_CALIBRATION: CalibrationSummary = {
  frames: { dark: 0, flat: 0, bias: 0, darkFlat: 0 },
  cosmeticCorrection: true,
};

export type StackPhase = 'collecting' | 'uploading' | 'reviewing' | 'processing' | 'done';

/** A frame the user has picked but not yet uploaded. */
export interface PendingFrame {
  id: string;
  name: string;
  sizeBytes: number;
  file: File;
}

export interface StackProgressState {
  percent: number;
  step: string;
  /** e.g. "340/1066" - which frame the current step is on. */
  detail?: string;
}

function chunk<T>(items: T[], size: number): T[][] {
  const batches: T[][] = [];
  for (let i = 0; i < items.length; i += size) {
    batches.push(items.slice(i, i + size));
  }
  return batches;
}

/**
 * Split files into upload requests of at most `maxCount` files and `maxBytes`
 * bytes (a file larger than `maxBytes` goes alone). Small requests keep the
 * progress bar moving and stay under a reverse proxy's body limit - Cloudflare
 * refuses anything over 100 MB, which 20 phone RAWs easily exceed. The cap is
 * the operator's per-file limit (Settings, `max_image_size_mb`): a request is
 * never heavier than one largest allowed file, so wherever a single image can
 * be uploaded, the batches can too.
 */
export function chunkBySize(files: File[], maxCount: number, maxBytes: number): File[][] {
  const batches: File[][] = [];
  let current: File[] = [];
  let bytes = 0;
  for (const file of files) {
    if (current.length > 0 && (current.length >= maxCount || bytes + file.size > maxBytes)) {
      batches.push(current);
      current = [];
      bytes = 0;
    }
    current.push(file);
    bytes += file.size;
  }
  if (current.length > 0) {
    batches.push(current);
  }
  return batches;
}

let pendingSeq = 0;

/**
 * Drives the stacking workflow: collect frames -> upload them in batches ->
 * review the thumbnail grid (exclude a trailed / clouded sub) -> stack ->
 * follow progress over the WebSocket. `maxFrames` is the operator's
 * `stacking_max_frames` (from `/api/config`), checked client-side so the user
 * gets a translated message instead of a raw backend 400.
 */
export function useStackProcessing(
  settings: StackSettings,
  maxFrames: number,
  maxImageSizeMb = 100,
) {
  const { t } = useTranslation();
  const [phase, setPhase] = useState<StackPhase>('collecting');
  const [pending, setPending] = useState<PendingFrame[]>([]);
  const [uploaded, setUploaded] = useState<StackFrameInfo[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [result, setResult] = useState<StackResult | null>(null);
  const [progress, setProgress] = useState<StackProgressState>({ percent: 0, step: '' });
  const [error, setError] = useState<string | null>(null);
  const [calibration, setCalibration] = useState<CalibrationSummary>(EMPTY_CALIBRATION);
  const stackIdRef = useRef<string | null>(null);
  const wsRef = useRef<WebSocketClient | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(
    () => () => {
      wsRef.current?.disconnect();
      if (pollRef.current) {
        clearInterval(pollRef.current);
      }
    },
    [],
  );

  const activeCount = uploaded.filter((frame) => !frame.excluded).length;

  const ensureStack = useCallback(async (): Promise<string> => {
    if (stackIdRef.current !== null) {
      return stackIdRef.current;
    }
    const session = await apiClient.initiateStack(Math.max(pending.length, MIN_FRAMES), settings);
    stackIdRef.current = session.stackId;
    return session.stackId;
  }, [pending.length, settings]);

  const addCalibrationFiles = useCallback(
    async (kind: CalibrationKind, files: File[]) => {
      if (files.length === 0) {
        return;
      }
      setError(null);
      try {
        const stackId = await ensureStack();
        // Same batch size as the light frames: the server caps files per request.
        for (const batch of chunk(files, UPLOAD_BATCH_SIZE)) {
          setCalibration(await apiClient.uploadCalibrationFrames(stackId, kind, batch));
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : t('stacking.errors.failed'));
      }
    },
    [ensureStack, t],
  );

  const clearCalibrationKind = useCallback(async (kind: CalibrationKind) => {
    const stackId = stackIdRef.current;
    if (stackId === null) {
      return;
    }
    try {
      setCalibration(await apiClient.clearCalibration(stackId, kind));
    } catch {
      /* leave the count as-is; the next stack response will reconcile it */
    }
  }, []);

  const addFiles = useCallback(
    (files: File[]) => {
      setError(null);
      setPending((prev) => {
        const total = prev.length + uploaded.length + files.length;
        if (total > maxFrames) {
          setError(t('stacking.errors.too_many', { count: total, max: maxFrames }));
          return prev;
        }
        return [
          ...prev,
          ...files.map((file) => ({
            id: `p${(pendingSeq += 1)}`,
            name: file.name,
            sizeBytes: file.size,
            file,
          })),
        ];
      });
    },
    [uploaded.length, maxFrames, t],
  );

  const removePending = useCallback((id: string) => {
    setPending((prev) => prev.filter((frame) => frame.id !== id));
  }, []);

  const uploadBatches = useCallback(
    async (stackId: string, files: File[], startIndex: number) => {
      // Progress follows the bytes, so it moves while a big batch is sent
      // instead of jumping from 0 to 100 when the only request answers.
      const totalBytes = Math.max(
        1,
        files.reduce((sum, file) => sum + file.size, 0),
      );
      let done = 0;
      let doneBytes = 0;
      const report = (bytes: number) =>
        setProgress({
          percent: Math.min(100, Math.round((bytes / totalBytes) * 100)),
          step: 'upload',
          detail: `${done}/${files.length}`,
        });
      report(0);
      // Never above the operator's per-file limit (Settings); smaller when that
      // still leaves fewer than MIN_UPLOAD_REQUESTS steps.
      const largest = files.reduce((max, file) => Math.max(max, file.size), 0);
      const budget = Math.min(
        maxImageSizeMb * MIB,
        Math.max(largest, Math.ceil(totalBytes / MIN_UPLOAD_REQUESTS)),
      );
      for (const batch of chunkBySize(files, UPLOAD_BATCH_SIZE, budget)) {
        const batchBytes = batch.reduce((sum, file) => sum + file.size, 0);
        await apiClient.uploadStackFrames(stackId, startIndex + done, batch, (sent, total) =>
          report(doneBytes + (SEND_SHARE * batchBytes * sent) / Math.max(total, 1)),
        );
        done += batch.length;
        doneBytes += batchBytes;
        report(doneBytes);
      }
    },
    [maxImageSizeMb],
  );

  const uploadFrames = useCallback(async () => {
    if (pending.length + uploaded.length < MIN_FRAMES) {
      setError(t('stacking.errors.too_few', { min: MIN_FRAMES }));
      return;
    }
    setError(null);
    setPhase('uploading');
    setProgress({ percent: 0, step: 'upload' });
    try {
      const stackId = await ensureStack();
      await uploadBatches(
        stackId,
        pending.map((frame) => frame.file),
        uploaded.length,
      );
      const stack = await apiClient.getStack(stackId);
      setUploaded(stack.frames);
      if (stack.calibration) {
        setCalibration(stack.calibration);
      }
      setPending([]);
      setSelected(stack.frames.length ? stack.frames[0].index : null);
      setPhase('reviewing');
    } catch (err) {
      setError(err instanceof Error ? err.message : t('stacking.errors.failed'));
      setPhase(uploaded.length ? 'reviewing' : 'collecting');
    }
  }, [pending, uploaded.length, ensureStack, uploadBatches, t]);

  const toggleExclude = useCallback(async (index: number, excluded: boolean) => {
    const stackId = stackIdRef.current;
    if (stackId === null) {
      return;
    }
    setUploaded((prev) =>
      prev.map((frame) => (frame.index === index ? { ...frame, excluded } : frame)),
    );
    try {
      await apiClient.excludeStackFrame(stackId, index, excluded);
    } catch {
      setUploaded((prev) =>
        prev.map((frame) => (frame.index === index ? { ...frame, excluded: !excluded } : frame)),
      );
    }
  }, []);

  const follow = useCallback((stackId: string, jobId: string) => {
    wsRef.current?.disconnect();
    const ws = stackStatusClient(jobId);
    wsRef.current = ws;
    ws.onStatusUpdate((status) => {
      setProgress({
        percent: status.progressPercent,
        step: status.currentStep,
        detail: status.detail,
      });
      if (TERMINAL.has(status.status)) {
        ws.disconnect();
        wsRef.current = null;
        apiClient
          .getStack(stackId)
          .then((final) => {
            setResult(final);
            setUploaded(final.frames);
            if (final.calibration) {
              setCalibration(final.calibration);
            }
            setPhase('done');
          })
          .catch(() => setPhase('done'));
      }
    });
    ws.connect();
  }, []);

  /** Poll a running stack that we have no job id for (a folder-watch auto-run). */
  const pollUntilDone = useCallback((stackId: string) => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
    }
    pollRef.current = setInterval(() => {
      void apiClient
        .getStack(stackId)
        .then((snapshot) => {
          if (!TERMINAL.has(snapshot.status)) {
            return;
          }
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
          setResult(snapshot);
          setUploaded(snapshot.frames);
          if (snapshot.calibration) {
            setCalibration(snapshot.calibration);
          }
          setProgress({ percent: 100, step: 'done' });
          setPhase(snapshot.status === 'completed' ? 'done' : 'reviewing');
        })
        .catch(() => undefined);
    }, 3000);
  }, []);

  /** Open an existing stack (a folder-watch session) instead of collecting new frames. */
  const attachToStack = useCallback(
    (snapshot: StackResult) => {
      wsRef.current?.disconnect();
      wsRef.current = null;
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      stackIdRef.current = snapshot.stackId;
      setError(null);
      setPending([]);
      setUploaded(snapshot.frames);
      setSelected(null);
      setResult(snapshot);
      if (snapshot.calibration) {
        setCalibration(snapshot.calibration);
      }
      if (snapshot.status === 'completed') {
        setProgress({ percent: 100, step: 'done' });
        setPhase('done');
      } else if (snapshot.status === 'processing') {
        setProgress({ percent: 0, step: 'registration' });
        setPhase('processing');
        pollUntilDone(snapshot.stackId);
      } else {
        setPhase('reviewing');
      }
    },
    [pollUntilDone],
  );

  const stack = useCallback(async () => {
    const stackId = stackIdRef.current;
    if (stackId === null || activeCount < MIN_FRAMES) {
      setError(t('stacking.errors.too_few', { min: MIN_FRAMES }));
      return;
    }
    setError(null);
    setResult(null);
    setSelected(null);
    setProgress({ percent: 0, step: '' });
    setPhase('processing');
    try {
      const started = await apiClient.processStack(stackId, settings);
      setResult(started);
      if (started.jobId && !TERMINAL.has(started.status)) {
        follow(stackId, started.jobId);
      } else {
        setUploaded(started.frames);
        setProgress({ percent: 100, step: 'done' });
        setPhase('done');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('stacking.errors.failed'));
      setPhase('reviewing');
    }
  }, [activeCount, settings, follow, t]);

  const selectFrame = useCallback((index: number | null) => {
    setSelected((prev) => (prev === index ? null : index));
  }, []);

  const reset = useCallback(() => {
    wsRef.current?.disconnect();
    wsRef.current = null;
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    stackIdRef.current = null;
    setPhase('collecting');
    setPending([]);
    setUploaded([]);
    setSelected(null);
    setResult(null);
    setProgress({ percent: 0, step: '' });
    setError(null);
    setCalibration(EMPTY_CALIBRATION);
  }, []);

  return {
    phase,
    pending,
    uploaded,
    selected,
    activeCount,
    calibration,
    result,
    progress,
    error,
    addFiles,
    removePending,
    uploadFrames,
    toggleExclude,
    addCalibrationFiles,
    clearCalibrationKind,
    select: selectFrame,
    stack,
    attachToStack,
    reset,
  };
}
