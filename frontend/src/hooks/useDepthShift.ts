import { useCallback, useState } from 'react';

import { apiClient } from '@/services/api';
import type { DepthStatistics, FocusPoint } from '@/types';

/** Requests depth-map generation and exposes the resulting layer URLs. */
export function useDepthShift(sessionId: string) {
  const [layerUrls, setLayerUrls] = useState<string[]>([]);
  const [statistics, setStatistics] = useState<DepthStatistics | null>(null);
  const [intensity, setIntensity] = useState(50);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generate = useCallback(
    async (numLayers = 7, focusPoint?: FocusPoint) => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await apiClient.generateDepthShift(
          sessionId,
          numLayers,
          intensity,
          focusPoint,
        );
        setLayerUrls(result.depthLayers.map((layer) => layer.imageUrl));
        setStatistics(result.statistics);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Depth shift failed');
      } finally {
        setIsLoading(false);
      }
    },
    [sessionId, intensity],
  );

  return { layerUrls, statistics, intensity, setIntensity, generate, isLoading, error };
}
