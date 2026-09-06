import { useCallback, useState } from 'react';

import { useTranslation } from '@/hooks/useTranslation';
import { apiClient } from '@/services/api';
import { errorMessage } from '@/services/apiError';

/** Analyses the session's original image and applies a computed one-click parameter set. */
export function useAutoAstro(sessionId: string) {
  const { t } = useTranslation();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apply = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      return await apiClient.applyAutoAstro(sessionId);
    } catch (err) {
      setError(errorMessage(err, t, 'Auto Astro failed'));
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, t]);

  return { apply, isLoading, error };
}
