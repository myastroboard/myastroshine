import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useServerConfig } from '@/hooks/useServerConfig';
import { apiClient } from '@/services/api';
import type { PublicConfig } from '@/types';

vi.mock('@/services/api', () => ({
  apiClient: { getConfig: vi.fn() },
}));

const mocked = vi.mocked(apiClient);

const DEFAULTS: PublicConfig = {
  maxImageSizeMb: 100,
  stackingEnabled: true,
  stackingMaxFrames: 2000,
  starlessEngines: ['classic'],
  denoiseEngines: ['classic'],
};

const LOADED: PublicConfig = {
  maxImageSizeMb: 250,
  stackingEnabled: false,
  stackingMaxFrames: 500,
  starlessEngines: ['classic', 'starnet2'],
  denoiseEngines: ['classic', 'deepsnr'],
};

describe('useServerConfig', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns the defaults before the request resolves', () => {
    mocked.getConfig.mockReturnValue(new Promise(() => {})); // never resolves
    const { result } = renderHook(() => useServerConfig());

    expect(result.current).toEqual(DEFAULTS);
  });

  it('swaps in the loaded config once the request resolves', async () => {
    mocked.getConfig.mockResolvedValue(LOADED);
    const { result } = renderHook(() => useServerConfig());

    await waitFor(() => expect(result.current).toEqual(LOADED));
  });

  it('keeps the defaults when the request fails', async () => {
    mocked.getConfig.mockRejectedValue(new Error('nope'));
    const { result } = renderHook(() => useServerConfig());

    // Give the rejected promise a tick to settle.
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(result.current).toEqual(DEFAULTS);
  });

  it('does not update state after unmount (cancelled guard)', async () => {
    let resolveConfig!: (value: PublicConfig) => void;
    mocked.getConfig.mockReturnValue(
      new Promise((resolve) => {
        resolveConfig = resolve;
      }),
    );

    const { result, unmount } = renderHook(() => useServerConfig());
    unmount();

    resolveConfig(LOADED);
    await new Promise((resolve) => setTimeout(resolve, 0));

    // The hook unmounted before the promise settled, so it never re-rendered
    // with the loaded config - reading `result.current` still returns the
    // last rendered (default) value, and no "update after unmount" warning.
    expect(result.current).toEqual(DEFAULTS);
  });
});
