import { useCallback, useState } from 'react';

import { apiClient } from '@/services/api';
import type { ProcessingParameters } from '@/types';

/** Sends the enhanced image back to AstroDex via the backend webhook route. */
export function useAstroDexIntegration() {
  const [isLoading, setIsLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendImage = useCallback(
    async (
      sessionId: string,
      astrodexImageId: string,
      parameters: ProcessingParameters,
      callbackUrl: string,
    ) => {
      setIsLoading(true);
      setSuccess(false);
      setError(null);
      try {
        await apiClient.sendToAstroDex(sessionId, astrodexImageId, parameters, callbackUrl);
        setSuccess(true);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to send to AstroDex');
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  return { sendImage, isLoading, success, error };
}
