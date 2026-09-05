import { useCallback, useState } from 'react';

import { apiClient } from '@/services/api';
import type { StarSourceInfo } from '@/types';

/** Requests a star-mask preview and exposes the detected sources. */
export function useStarMask(sessionId: string) {
  const [stars, setStars] = useState<StarSourceInfo[]>([]);
  const [sourceCount, setSourceCount] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const detect = useCallback(
    async (sensitivity: number, maxSize: number) => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await apiClient.detectStars(sessionId, sensitivity, maxSize);
        setStars(result.stars);
        setSourceCount(result.sourceCount);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Star detection failed');
      } finally {
        setIsLoading(false);
      }
    },
    [sessionId],
  );

  const clear = useCallback(() => {
    setStars([]);
    setSourceCount(null);
    setError(null);
  }, []);

  return { stars, sourceCount, detect, clear, isLoading, error };
}
