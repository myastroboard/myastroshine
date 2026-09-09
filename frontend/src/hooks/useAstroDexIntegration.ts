import { useCallback, useState } from 'react';

import { apiClient } from '@/services/api';

/** Sends the enhanced image back to AstroDex via the backend handoff route. */
export function useAstroDexIntegration() {
  const [isLoading, setIsLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const returnImage = useCallback(async (sessionId: string): Promise<boolean> => {
    setIsLoading(true);
    setSuccess(false);
    setError(null);
    try {
      await apiClient.returnToAstrodex(sessionId);
      setSuccess(true);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send back to AstroDex');
      return false;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { returnImage, isLoading, success, error };
}
