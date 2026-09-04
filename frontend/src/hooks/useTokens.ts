import { useCallback, useEffect, useState } from 'react';

import { apiClient } from '@/services/api';
import type { CreatedToken, WebhookToken } from '@/types';

/**
 * Manages the AstroDex webhook tokens. `justCreated` holds the last created
 * token's secret material - shown once, then cleared by `dismissCreated`.
 */
export function useTokens() {
  const [tokens, setTokens] = useState<WebhookToken[]>([]);
  const [justCreated, setJustCreated] = useState<CreatedToken | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      setTokens((await apiClient.listTokens()).tokens);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load tokens');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const createToken = useCallback(
    async (name: string, expiresInDays?: number) => {
      const created = await apiClient.createToken(name, expiresInDays);
      setJustCreated(created);
      await refresh();
      return created;
    },
    [refresh],
  );

  const revokeToken = useCallback(
    async (tokenId: string) => {
      await apiClient.revokeToken(tokenId);
      await refresh();
    },
    [refresh],
  );

  return {
    tokens,
    justCreated,
    dismissCreated: () => setJustCreated(null),
    createToken,
    revokeToken,
    refresh,
    isLoading,
    error,
  };
}
