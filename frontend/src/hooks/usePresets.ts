import { useCallback, useEffect, useState } from 'react';

import { apiClient } from '@/services/api';
import type { Preset } from '@/types';

/** Loads presets and applies them to the active session. */
export function usePresets(sessionId: string) {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [activePreset, setActivePreset] = useState<string>();
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    apiClient
      .listPresets()
      .then((result) => {
        if (!cancelled) {
          setPresets(result.presets);
        }
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const applyPreset = useCallback(
    async (presetId: string) => {
      setActivePreset(presetId);
      await fetch(
        `${import.meta.env.VITE_API_URL ?? '/api'}/presets/${presetId}/apply/${sessionId}`,
        { method: 'POST' },
      );
    },
    [sessionId],
  );

  return { presets, activePreset, applyPreset, isLoading };
}
