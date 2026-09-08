import { useEffect, useState } from 'react';

import { apiClient } from '@/services/api';
import type { StackResult } from '@/types';

const POLL_MS = 15_000;

/**
 * Polls for the current folder-watch stack (`GET /api/stack/latest`). Returns
 * `null` when watch ingest is off or empty. Pass `active: false` to pause the
 * poll (e.g. once the user is already working on a stack).
 */
export function useWatchStack(active: boolean): StackResult | null {
  const [watch, setWatch] = useState<StackResult | null>(null);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    let alive = true;
    const tick = () => {
      void apiClient
        .getLatestWatchStack()
        .then((result) => {
          if (alive) {
            setWatch(result);
          }
        })
        .catch(() => undefined);
    };
    tick();
    const id = setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [active]);

  return active ? watch : null;
}
