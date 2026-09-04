import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TokenManager } from '@/components/TokenManager';
import { apiClient } from '@/services/api';

vi.mock('@/services/api', () => ({
  apiClient: {
    listTokens: vi.fn(),
    createToken: vi.fn(),
    revokeToken: vi.fn(),
  },
}));

const mocked = vi.mocked(apiClient);

describe('TokenManager', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.listTokens.mockResolvedValue({ tokens: [], total: 0 });
  });

  it('creates a token and shows its secret once', async () => {
    mocked.createToken.mockResolvedValue({
      id: 't1',
      name: 'AstroDex prod',
      tokenPrefix: 'mas_abcd',
      createdAt: '2026-09-03T00:00:00Z',
      lastUsedAt: null,
      expiresAt: null,
      revoked: false,
      token: 'mas_secret-value',
      signingSecret: 'deadbeef',
    });

    render(<TokenManager />);
    fireEvent.change(screen.getByPlaceholderText('AstroDex prod'), {
      target: { value: 'AstroDex prod' },
    });
    fireEvent.click(screen.getByRole('button', { name: /create token/i }));

    await waitFor(() => {
      expect(screen.getByText(/not shown again/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/mas_secret-value/)).toBeInTheDocument();
    expect(mocked.createToken).toHaveBeenCalledWith('AstroDex prod', undefined);
  });
});
