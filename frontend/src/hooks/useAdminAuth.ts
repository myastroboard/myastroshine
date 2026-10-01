import { useCallback, useEffect, useState } from 'react';

import { ApiError, apiClient, onAdminLoginRequired } from '@/services/api';
import type { AuthStatus } from '@/types';

/**
 * The admin gate in front of Settings. Loads `/api/auth/status`, exposes setup /
 * login / logout, and drops back to "not authenticated" as soon as any admin
 * call reports the session gone (expired, revoked from another browser).
 *
 * `setup` and `login` reject with the `ApiError` so the form can show why;
 * `error` only holds a failure to load the status itself.
 */
export function useAdminAuth() {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [error, setError] = useState<unknown>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      setStatus(await apiClient.getAuthStatus());
    } catch (err) {
      setError(err);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(
    () =>
      onAdminLoginRequired(() => {
        setStatus((current) => (current ? { ...current, authenticated: false } : current));
      }),
    [],
  );

  const setup = useCallback(
    async (password: string) => {
      try {
        await apiClient.setupAdmin(password);
      } catch (err) {
        if (err instanceof ApiError && err.code === 'ADMIN_ALREADY_CONFIGURED') {
          // Someone set the password since this page loaded (another browser, a
          // second tab): switch to the login form instead of a dead end.
          await refresh();
          return;
        }
        throw err;
      }
      await refresh();
    },
    [refresh],
  );

  const login = useCallback(
    async (password: string) => {
      await apiClient.loginAdmin(password);
      await refresh();
    },
    [refresh],
  );

  const logout = useCallback(async () => {
    try {
      await apiClient.logoutAdmin();
    } finally {
      await refresh();
    }
  }, [refresh]);

  return { status, error, refresh, setup, login, logout };
}
