import { useCallback, useState } from 'react';

import { apiClient } from '@/services/api';

/** Analyses the session's original image and applies a computed one-click parameter set. */
export function useAutoAstro(sessionId: string) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apply = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      return await apiClient.applyAutoAstro(sessionId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Auto Astro failed');
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  return { apply, isLoading, error };
}
