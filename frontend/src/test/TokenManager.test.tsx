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

  it('passes the expiry in days when one is set', async () => {
    mocked.createToken.mockResolvedValue({
      id: 't2',
      name: 'temp',
      tokenPrefix: 'mas_temp',
      createdAt: '2026-09-03T00:00:00Z',
      lastUsedAt: null,
      expiresAt: '2026-10-03T00:00:00Z',
      revoked: false,
      token: 'mas_t',
      signingSecret: 'beef',
    });
    render(<TokenManager />);

    fireEvent.change(screen.getByPlaceholderText('AstroDex prod'), { target: { value: '  temp  ' } });
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '30' } });
    fireEvent.click(screen.getByRole('button', { name: /create token/i }));

    await waitFor(() => expect(mocked.createToken).toHaveBeenCalledWith('temp', 30));
  });

  it('ignores a blank name submitted with Enter', () => {
    render(<TokenManager />);
    const field = screen.getByPlaceholderText('AstroDex prod');

    fireEvent.change(field, { target: { value: '   ' } });
    fireEvent.submit(field.closest('form') as HTMLFormElement);

    expect(mocked.createToken).not.toHaveBeenCalled();
  });

  it('hides the secret once dismissed', async () => {
    mocked.createToken.mockResolvedValue({
      id: 't3',
      name: 'x',
      tokenPrefix: 'mas_x',
      createdAt: '2026-09-03T00:00:00Z',
      lastUsedAt: null,
      expiresAt: null,
      revoked: false,
      token: 'mas_shown_once',
      signingSecret: 'cafe',
    });
    render(<TokenManager />);
    fireEvent.change(screen.getByPlaceholderText('AstroDex prod'), { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: /create token/i }));
    await screen.findByText(/mas_shown_once/);

    fireEvent.click(screen.getByRole('button', { name: /done/i }));

    expect(screen.queryByText(/mas_shown_once/)).not.toBeInTheDocument();
  });

  it('lists live, expiring and revoked tokens and revokes a live one', async () => {
    mocked.listTokens.mockResolvedValue({
      tokens: [
        {
          id: 'live',
          name: 'Board',
          tokenPrefix: 'mas_live',
          createdAt: '2026-09-03T00:00:00Z',
          lastUsedAt: null,
          expiresAt: '2026-12-31T00:00:00Z',
          revoked: false,
        },
        {
          id: 'old',
          name: 'Old board',
          tokenPrefix: 'mas_old0',
          createdAt: '2026-08-01T00:00:00Z',
          lastUsedAt: null,
          expiresAt: null,
          revoked: true,
        },
      ],
      total: 2,
    });
    mocked.revokeToken.mockResolvedValue(undefined);
    render(<TokenManager />);

    expect(await screen.findByText(/2026-12-31/)).toBeInTheDocument();
    expect(screen.getByText('Old board', { exact: false })).toHaveClass('line-through');
    const revokeButtons = screen.getAllByRole('button', { name: /revoke/i });
    expect(revokeButtons).toHaveLength(1);

    fireEvent.click(revokeButtons[0]);

    await waitFor(() => expect(mocked.revokeToken).toHaveBeenCalledWith('live'));
  });

  it('shows a failure to load the tokens', async () => {
    mocked.listTokens.mockRejectedValue(new Error('Admin login required'));
    render(<TokenManager />);

    expect(await screen.findByText('Admin login required')).toBeInTheDocument();
  });
});

