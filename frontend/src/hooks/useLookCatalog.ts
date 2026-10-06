import { useEffect, useState } from 'react';

import { apiClient } from '@/services/api';
import { GENERAL_LOOK_CATALOG, type LookCatalog } from '@/types';

/**
 * The "Style" gallery's looks for this session (`GET /api/looks/{id}`): the
 * night-landscape looks first when the photo has a sky mask, then the general
 * ones. Until it loads, or if the request fails, the general looks - they suit
 * every image, so the gallery is never empty.
 */
export function useLookCatalog(sessionId: string): LookCatalog {
  const [catalog, setCatalog] = useState<LookCatalog>(GENERAL_LOOK_CATALOG);

  useEffect(() => {
    let cancelled = false;
    setCatalog(GENERAL_LOOK_CATALOG);
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
