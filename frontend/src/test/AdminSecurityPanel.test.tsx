import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AdminSecurityPanel } from '@/components/AdminSecurityPanel';
import { ApiError, apiClient } from '@/services/api';
import type { AdminSession } from '@/types';

vi.mock('@/services/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/api')>()),
  apiClient: {
    changeAdminPassword: vi.fn(),
    listAdminSessions: vi.fn(),
    revokeAdminSession: vi.fn(),
  },
}));

const mocked = vi.mocked(apiClient);

const MINE: AdminSession = {
  id: 'mine',
  clientIp: '10.0.0.2',
  userAgent: 'Firefox',
  createdAt: '2026-09-30T10:00:00Z',
  lastSeenAt: '2026-09-30T11:00:00Z',
  current: true,
};
const OTHER: AdminSession = { ...MINE, id: 'other', clientIp: null, userAgent: null, current: false };

function type(label: RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

describe('AdminSecurityPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.listAdminSessions.mockResolvedValue([MINE, OTHER]);
    mocked.revokeAdminSession.mockResolvedValue(undefined);
    mocked.changeAdminPassword.mockResolvedValue(undefined);
  });

  it('lists the logged-in browsers and flags this one', async () => {
    render(<AdminSecurityPanel onSignedOut={vi.fn()} />);

    expect(await screen.findByText('Firefox')).toBeInTheDocument();
    expect(screen.getByText('this browser')).toBeInTheDocument();
    expect(screen.getByText('Unknown browser')).toBeInTheDocument();
  });

  it('logs another browser out and reloads the list', async () => {
    const onSignedOut = vi.fn();
    render(<AdminSecurityPanel onSignedOut={onSignedOut} />);
    await screen.findByText('Unknown browser');
    mocked.listAdminSessions.mockResolvedValue([MINE]);

    fireEvent.click(screen.getAllByRole('button', { name: /log out/i })[1]);

    await waitFor(() => expect(screen.queryByText('Unknown browser')).not.toBeInTheDocument());
    expect(mocked.revokeAdminSession).toHaveBeenCalledWith('other');
    expect(onSignedOut).not.toHaveBeenCalled();
  });

  it('logging this browser out signs the page out', async () => {
    const onSignedOut = vi.fn();
    render(<AdminSecurityPanel onSignedOut={onSignedOut} />);
    await screen.findByText('Firefox');

    fireEvent.click(screen.getAllByRole('button', { name: /log out/i })[0]);

    await waitFor(() => expect(onSignedOut).toHaveBeenCalled());
  });

  it('reports a failure to list or revoke', async () => {
    mocked.listAdminSessions.mockRejectedValueOnce(new ApiError(500, 'boom'));
    const { unmount } = render(<AdminSecurityPanel onSignedOut={vi.fn()} />);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    unmount();

    mocked.revokeAdminSession.mockRejectedValue(new ApiError(404, 'Admin session x not found'));
    render(<AdminSecurityPanel onSignedOut={vi.fn()} />);
    await screen.findByText('Firefox');
    fireEvent.click(screen.getAllByRole('button', { name: /log out/i })[1]);
    expect(await screen.findByRole('alert')).toHaveTextContent('Admin session x not found');
  });

  it('changes the password and clears the form', async () => {
    render(<AdminSecurityPanel onSignedOut={vi.fn()} />);

    type(/current password/i, 'old password');
    type(/^new password$/i, 'a new long password');
    type(/confirm the password/i, 'a new long password');
    fireEvent.click(screen.getByRole('button', { name: /change password/i }));

    expect(await screen.findByRole('status')).toHaveTextContent(/password changed/i);
    expect(mocked.changeAdminPassword).toHaveBeenCalledWith('old password', 'a new long password');
    expect(screen.getByLabelText(/current password/i)).toHaveValue('');
  });

  it('checks the new password locally, then shows a wrong current password', async () => {
    render(<AdminSecurityPanel onSignedOut={vi.fn()} />);
    await screen.findByText('Firefox');

    type(/current password/i, 'old password');
    type(/^new password$/i, 'short');
    fireEvent.click(screen.getByRole('button', { name: /change password/i }));
    expect(screen.getByRole('alert')).toHaveTextContent(/at least 10/i);
    expect(mocked.changeAdminPassword).not.toHaveBeenCalled();

    mocked.changeAdminPassword.mockRejectedValue(new ApiError(401, 'x', 'INVALID_CREDENTIALS'));
    type(/^new password$/i, 'a new long password');
    type(/confirm the password/i, 'a new long password');
    fireEvent.click(screen.getByRole('button', { name: /change password/i }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/wrong password/i));
  });
});
