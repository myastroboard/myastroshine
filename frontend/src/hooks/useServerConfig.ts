import { useEffect, useState } from 'react';

import { apiClient } from '@/services/api';
import type { PublicConfig } from '@/types';

/** Matches the backend `AppSettings` field defaults - used until `/api/config`
 * responds, and as a fallback if it fails. */
const DEFAULTS: PublicConfig = {
  maxImageSizeMb: 100,
  stackingEnabled: true,
  stackingMaxFrames: 2000,
};

/**
 * Fetches the public runtime limits once on mount. Returns the defaults while
 * loading or if the request fails, so callers never have to handle a null.
 */
export function useServerConfig(): PublicConfig {
  const [config, setConfig] = useState<PublicConfig>(DEFAULTS);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .getConfig()
      .then((loaded) => {
        if (!cancelled) {
          setConfig(loaded);
        }
      })
      .catch(() => {
        /* keep the defaults */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return config;
}
