import { useEffect, useState } from 'react';

import { apiClient } from '@/services/api';
import { DEFAULT_LOOK_CATALOG, type LookCatalog } from '@/types';

/**
 * The "Style" gallery's looks for this session (`GET /api/looks/{id}`), grouped
 * by kind of picture - the night-landscape group first when the photo has a sky
 * mask. Until it loads, or if the request fails, every session's groups, so
 * the gallery is never empty.
 */
export function useLookCatalog(sessionId: string): LookCatalog {
  const [catalog, setCatalog] = useState<LookCatalog>(DEFAULT_LOOK_CATALOG);

  useEffect(() => {
    let cancelled = false;
    setCatalog(DEFAULT_LOOK_CATALOG);
    apiClient
      .getLookCatalog(sessionId)
      .then((loaded) => {
        if (!cancelled) {
          setCatalog(loaded);
        }
      })
      .catch(() => {
        /* keep the general looks */
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  return catalog;
}
