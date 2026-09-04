import { useCallback, useEffect, useState } from 'react';

import { apiClient } from '@/services/api';
import type { LogLevel, LogLevels } from '@/types';

/**
 * Backs the Logs section: a tail of the rotating log file (newest first), the
 * current sink levels, and the clear / export actions. The file and console
 * levels are changed from Advanced (they are part of app_settings).
 */
export function useLogs() {
  const [lines, setLines] = useState<string[]>([]);
  const [level, setLevel] = useState<LogLevel | ''>('');
  const [levels, setLevels] = useState<LogLevels | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    try {
      const [tail, current] = await Promise.all([
        apiClient.getLogs(300, level || undefined),
        apiClient.getLogLevels(),
      ]);
      setLines(tail.lines);
      setLevels(current);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load logs');
    } finally {
      setIsLoading(false);
    }
  }, [level]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const clear = useCallback(async () => {
    setBusy(true);
    try {
      await apiClient.clearLogs();
      await refresh();
    } finally {
      setBusy(false);
    }
  }, [refresh]);

  const exportZip = useCallback(async () => {
    const blob = await apiClient.exportLogs();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'myastroshine-logs.zip';
    anchor.click();
    URL.revokeObjectURL(url);
  }, []);

  return { lines, level, setLevel, levels, refresh, clear, exportZip, isLoading, busy, error };
}
