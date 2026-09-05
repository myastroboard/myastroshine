import { useEffect, useState } from 'react';

import { apiClient } from '@/services/api';
import type { VersionCheckResult } from '@/types';

// Matches the backend's cache TTL (app/constants.py:VERSION_CHECK_CACHE_TTL_SECONDS) -
// polling more often would just re-read the same cached result.
const POLL_INTERVAL_MS = 4 * 60 * 60 * 1000;

/** True if `latest` is a strictly newer MAJOR.MINOR.PATCH than `current`. */
function isNewer(latest: string, current: string): boolean {
  const toParts = (version: string) =>
    version
      .replace(/^v/, '')
      .split('.')
      .map((part) => Number(part) || 0);
  const [latestParts, currentParts] = [toParts(latest), toParts(current)];
  for (let i = 0; i < Math.max(latestParts.length, currentParts.length); i += 1) {
    const [l, c] = [latestParts[i] ?? 0, currentParts[i] ?? 0];
    if (l !== c) {
      return l > c;
    }
  }
  return false;
}

/**
 * Polls the (backend-cached) update-check endpoint every 4h. Re-verifies
 * `updateAvailable` client-side rather than trusting it outright, so a
 * banner can never claim an update is available when it isn't (or vice
 * versa). Fails silently - checking for updates is a non-critical
 * nice-to-have, never worth surfacing an error for.
 */
export function useVersionCheck() {
  const [result, setResult] = useState<VersionCheckResult | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const response = await apiClient.checkForUpdates();
        if (!cancelled) {
          setResult(response);
        }
      } catch {
        // Non-critical - the banner just doesn't show.
      }
    }

    void check();
    const interval = setInterval(() => void check(), POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const updateAvailable =
    result?.updateAvailable === true &&
    result.latestVersion !== null &&
    isNewer(result.latestVersion, result.currentVersion);

  return { updateAvailable, result };
}
