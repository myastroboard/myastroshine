import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useTokens } from '@/hooks/useTokens';
import { apiClient } from '@/services/api';
import type { CreatedToken, WebhookToken } from '@/types';

vi.mock('@/services/api', () => ({
  apiClient: {
    listTokens: vi.fn(),
    createToken: vi.fn(),
    revokeToken: vi.fn(),
  },
}));

const mocked = vi.mocked(apiClient);

const TOKEN: WebhookToken = {
  id: 't1',
  name: 'AstroDex prod',
  tokenPrefix: 'mas_abcd',
  createdAt: '2026-09-03T00:00:00Z',
  lastUsedAt: null,
  expiresAt: null,
  revoked: false,
};

const CREATED: CreatedToken = {
  ...TOKEN,
  token: 'mas_secret-value',
  signingSecret: 'deadbeef',
};

describe('useTokens', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.listTokens.mockResolvedValue({ tokens: [TOKEN], total: 1 });
  });

  it('loads tokens on mount', async () => {
    const { result } = renderHook(() => useTokens());

    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.tokens).toEqual([TOKEN]);
    expect(result.current.error).toBeNull();
    expect(result.current.justCreated).toBeNull();
  });

  it('surfaces an Error instance message on failure', async () => {
    mocked.listTokens.mockRejectedValue(new Error('server down'));
    const { result } = renderHook(() => useTokens());

    await waitFor(() => expect(result.current.error).toBe('server down'));
    expect(result.current.tokens).toEqual([]);
  });

  it('falls back to a generic message when a non-Error is thrown', async () => {
    mocked.listTokens.mockRejectedValue('boom');
    const { result } = renderHook(() => useTokens());

    await waitFor(() => expect(result.current.error).toBe('Failed to load tokens'));
  });

  it('createToken stores the secret once and reloads the list', async () => {
    mocked.createToken.mockResolvedValue(CREATED);
    const { result } = renderHook(() => useTokens());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    mocked.listTokens.mockClear();
    let created: CreatedToken | undefined;
    await act(async () => {
      created = await result.current.createToken('AstroDex prod', 30);
    });

    expect(created).toEqual(CREATED);
    expect(mocked.createToken).toHaveBeenCalledWith('AstroDex prod', 30);
    expect(result.current.justCreated).toEqual(CREATED);
    expect(mocked.listTokens).toHaveBeenCalledTimes(1); // refreshed after creating
  });

  it('createToken works without an explicit expiry', async () => {
    mocked.createToken.mockResolvedValue(CREATED);
    const { result } = renderHook(() => useTokens());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.createToken('No expiry');
    });

    expect(mocked.createToken).toHaveBeenCalledWith('No expiry', undefined);
  });

  it('dismissCreated clears the just-created token', async () => {
    mocked.createToken.mockResolvedValue(CREATED);
    const { result } = renderHook(() => useTokens());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.createToken('AstroDex prod');
    });
    expect(result.current.justCreated).not.toBeNull();

    act(() => result.current.dismissCreated());
    expect(result.current.justCreated).toBeNull();
  });

  it('revokeToken revokes and reloads the list', async () => {
    mocked.revokeToken.mockResolvedValue(undefined);
    const { result } = renderHook(() => useTokens());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    mocked.listTokens.mockClear();
    await act(async () => {
      await result.current.revokeToken('t1');
    });

    expect(mocked.revokeToken).toHaveBeenCalledWith('t1');
    expect(mocked.listTokens).toHaveBeenCalledTimes(1);
  });
});
