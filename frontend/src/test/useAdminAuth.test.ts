import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAdminAuth } from '@/hooks/useAdminAuth';
import { ApiError, apiClient, onAdminLoginRequired } from '@/services/api';

vi.mock('@/services/api', async (importOriginal) => ({
  ApiError: (await importOriginal<typeof import('@/services/api')>()).ApiError,
  apiClient: {
    getAuthStatus: vi.fn(),
    setupAdmin: vi.fn(),
    loginAdmin: vi.fn(),
    logoutAdmin: vi.fn(),
  },
  onAdminLoginRequired: vi.fn(),
}));

const mocked = vi.mocked(apiClient);
const subscribe = vi.mocked(onAdminLoginRequired);

const LOGGED_OUT = { adminEnabled: true, configured: true, authenticated: false };
const LOGGED_IN = { adminEnabled: true, configured: true, authenticated: true };

describe('useAdminAuth', () => {
  let loginRequired: () => void = () => undefined;
  const unsubscribe = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    subscribe.mockImplementation((listener) => {
      loginRequired = listener;
      return unsubscribe;
    });
    mocked.getAuthStatus.mockResolvedValue(LOGGED_OUT);
  });

  it('loads the status on mount', async () => {
    const { result } = renderHook(() => useAdminAuth());

    await waitFor(() => expect(result.current.status).toEqual(LOGGED_OUT));
    expect(result.current.error).toBeNull();
  });

  it('exposes a failure to load the status', async () => {
    const failure = new Error('down');
    mocked.getAuthStatus.mockRejectedValueOnce(failure);

    const { result } = renderHook(() => useAdminAuth());

    await waitFor(() => expect(result.current.error).toBe(failure));
    expect(result.current.status).toBeNull();
  });

  it('login calls the API then reloads the status', async () => {
    mocked.loginAdmin.mockResolvedValue(undefined);
    const { result } = renderHook(() => useAdminAuth());
    await waitFor(() => expect(result.current.status).not.toBeNull());
    mocked.getAuthStatus.mockResolvedValue(LOGGED_IN);

    await act(() => result.current.login('pw'));

    expect(mocked.loginAdmin).toHaveBeenCalledWith('pw');
    expect(result.current.status).toEqual(LOGGED_IN);
  });

  it('setup calls the API then reloads the status', async () => {
    mocked.setupAdmin.mockResolvedValue(undefined);
    const { result } = renderHook(() => useAdminAuth());
    mocked.getAuthStatus.mockResolvedValue(LOGGED_IN);

    await act(() => result.current.setup('a long password'));

    expect(mocked.setupAdmin).toHaveBeenCalledWith('a long password');
    expect(result.current.status).toEqual(LOGGED_IN);
  });

  it('switches to the login form when the password was set meanwhile', async () => {
    mocked.setupAdmin.mockRejectedValue(new ApiError(409, 'set', 'ADMIN_ALREADY_CONFIGURED'));
    mocked.getAuthStatus.mockResolvedValue({ adminEnabled: true, configured: false, authenticated: false });
    const { result } = renderHook(() => useAdminAuth());
    await waitFor(() => expect(result.current.status?.configured).toBe(false));
    mocked.getAuthStatus.mockResolvedValue(LOGGED_OUT);

    await act(() => result.current.setup('a long password'));

    expect(result.current.status).toEqual(LOGGED_OUT);
  });

  it('setup rejects with any other API error', async () => {
    mocked.setupAdmin.mockRejectedValue(new ApiError(400, 'too short', 'INVALID_PARAMETER'));
    const { result } = renderHook(() => useAdminAuth());
    await waitFor(() => expect(result.current.status).not.toBeNull());

    await expect(result.current.setup('short')).rejects.toThrow('too short');
  });

  it('login rejects with the API error and leaves the status alone', async () => {
    mocked.loginAdmin.mockRejectedValue(new Error('wrong'));
    const { result } = renderHook(() => useAdminAuth());
    await waitFor(() => expect(result.current.status).not.toBeNull());

    await expect(result.current.login('bad')).rejects.toThrow('wrong');
    expect(result.current.status).toEqual(LOGGED_OUT);
  });

  it('logout reloads the status even when the API call fails', async () => {
    mocked.getAuthStatus.mockResolvedValue(LOGGED_IN);
    mocked.logoutAdmin.mockRejectedValue(new Error('offline'));
    const { result } = renderHook(() => useAdminAuth());
    await waitFor(() => expect(result.current.status).toEqual(LOGGED_IN));
    mocked.getAuthStatus.mockResolvedValue(LOGGED_OUT);

    await act(async () => {
      await result.current.logout().catch(() => undefined);
    });

    expect(result.current.status).toEqual(LOGGED_OUT);
  });

  it('falls back to logged out when an admin call reports the session gone', async () => {
    mocked.getAuthStatus.mockResolvedValue(LOGGED_IN);
    const { result, unmount } = renderHook(() => useAdminAuth());
    await waitFor(() => expect(result.current.status).toEqual(LOGGED_IN));

    act(() => loginRequired());

    expect(result.current.status).toEqual(LOGGED_OUT);
    unmount();
    expect(unsubscribe).toHaveBeenCalled();
  });

  it('ignores a session-gone signal before the status is known', () => {
    mocked.getAuthStatus.mockReturnValue(new Promise(() => undefined));
    const { result } = renderHook(() => useAdminAuth());

    act(() => loginRequired());

    expect(result.current.status).toBeNull();
  });
});
