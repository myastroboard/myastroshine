import { useCallback, useEffect, useState } from 'react';

import { apiClient, type SavePresetInput } from '@/services/api';
import type { Preset } from '@/types';

/** Loads presets and applies / saves / deletes them for the active session. */
export function usePresets(sessionId: string) {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [activePreset, setActivePreset] = useState<string>();
  const [isLoading, setIsLoading] = useState(false);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    try {
      setPresets((await apiClient.listPresets()).presets);
    } catch {
      // Leave the current list in place on a transient failure.
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const applyPreset = useCallback(
    async (presetId: string) => {
      setActivePreset(presetId);
      await apiClient.applyPreset(presetId, sessionId);
    },
    [sessionId],
  );

  const savePreset = useCallback(
    async (input: SavePresetInput) => {
      await apiClient.savePreset(input);
      await refresh();
    },
    [refresh],
  );

  const deletePreset = useCallback(
    async (presetId: string) => {
      setActivePreset((current) => (current === presetId ? undefined : current));
      await apiClient.deletePreset(presetId);
      await refresh();
    },
    [refresh],
  );

  /** Drop the active-preset highlight once the parameters diverge from it. */
  const clearActivePreset = useCallback(() => setActivePreset(undefined), []);

  return {
    presets,
    activePreset,
    applyPreset,
    savePreset,
    deletePreset,
    clearActivePreset,
    isLoading,
    refresh,
  };
}
