import { useEffect, useState } from 'react';

import { apiClient } from '@/services/api';
import type { CaptureInfo } from '@/types';

/**
 * Fetches the session's capture info once on mount. `null` while loading, on
 * a session with none, or if the request fails - the info panel just stays
 * hidden rather than surfacing an error for what is a nice-to-have.
 */
export function useCaptureInfo(sessionId: string, enabled: boolean): CaptureInfo | null {
  const [info, setInfo] = useState<CaptureInfo | null>(null);

  useEffect(() => {
    if (!enabled) {
      setInfo(null);
      return;
    }
    let cancelled = false;
    apiClient
      .getCaptureInfo(sessionId)
      .then((loaded) => {
        if (!cancelled) {
          setInfo(loaded);
        }
      })
      .catch(() => {
        /* stay hidden */
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, enabled]);

  return info;
}
