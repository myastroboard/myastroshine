import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useLookCatalog } from '@/hooks/useLookCatalog';
import { apiClient } from '@/services/api';
import { GENERAL_LOOK_CATALOG, type LookCatalog } from '@/types';

vi.mock('@/services/api', () => ({
  apiClient: { getLookCatalog: vi.fn() },
}));

const mocked = vi.mocked(apiClient);
const NIGHT: LookCatalog = { scene: 'nightscape', looks: ['galactic_core', 'blue_hour', 'vivid'] };

describe('useLookCatalog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('offers the general looks until the catalogue loads, then the session ones', async () => {
    mocked.getLookCatalog.mockResolvedValue(NIGHT);

    const { result } = renderHook(() => useLookCatalog('s1'));

    expect(result.current).toEqual(GENERAL_LOOK_CATALOG);
    await waitFor(() => expect(result.current).toEqual(NIGHT));
    expect(mocked.getLookCatalog).toHaveBeenCalledWith('s1');
  });

  it('keeps the general looks when the request fails', async () => {
    mocked.getLookCatalog.mockRejectedValue(new Error('offline'));

    const { result } = renderHook(() => useLookCatalog('s1'));

    await waitFor(() => expect(mocked.getLookCatalog).toHaveBeenCalled());
    expect(result.current).toEqual(GENERAL_LOOK_CATALOG);
  });

  it('ignores a late answer for a session it has left', async () => {
    let resolveFirst: (value: LookCatalog) => void = () => undefined;
    mocked.getLookCatalog
      .mockImplementationOnce(() => new Promise((resolve) => (resolveFirst = resolve)))
      .mockResolvedValueOnce(GENERAL_LOOK_CATALOG);

    const { result, rerender } = renderHook(({ id }) => useLookCatalog(id), {
      initialProps: { id: 's1' },
    });
    rerender({ id: 's2' });
    resolveFirst(NIGHT);

    await waitFor(() => expect(mocked.getLookCatalog).toHaveBeenCalledTimes(2));
    expect(result.current).toEqual(GENERAL_LOOK_CATALOG);
  });
});
