import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AdminLoginForm, AdminSetupForm } from '@/components/AdminAuthForms';
import { ApiError } from '@/services/api';

function type(label: RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

describe('AdminSetupForm', () => {
  it('refuses a mismatched confirmation without calling the server', () => {
    const onSubmit = vi.fn();
    render(<AdminSetupForm onSubmit={onSubmit} />);

    type(/^new password$/i, 'a long password');
    type(/confirm the password/i, 'another password');
    fireEvent.click(screen.getByRole('button', { name: /create and log in/i }));

    expect(screen.getByRole('alert')).toHaveTextContent(/do not match/i);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('submits a valid password', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<AdminSetupForm onSubmit={onSubmit} />);

    type(/^new password$/i, 'a long password');
    type(/confirm the password/i, 'a long password');
    fireEvent.click(screen.getByRole('button', { name: /create and log in/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith('a long password'));
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('shows the server error and lets the user retry', async () => {
    const onSubmit = vi.fn().mockRejectedValue(new ApiError(409, 'x', 'ADMIN_ALREADY_CONFIGURED'));
    render(<AdminSetupForm onSubmit={onSubmit} />);

    type(/^new password$/i, 'a long password');
    type(/confirm the password/i, 'a long password');
    fireEvent.click(screen.getByRole('button', { name: /create and log in/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/already exists/i);
    expect(screen.getByRole('button', { name: /create and log in/i })).toBeEnabled();
  });
});

describe('AdminLoginForm', () => {
  it('does nothing on an empty password', () => {
    const onSubmit = vi.fn();
    render(<AdminLoginForm onSubmit={onSubmit} />);

    fireEvent.click(screen.getByRole('button', { name: /log in/i }));

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('submits the password', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<AdminLoginForm onSubmit={onSubmit} />);

    type(/admin password/i, 'secret value');
    fireEvent.click(screen.getByRole('button', { name: /log in/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith('secret value'));
  });

  it('shows a wrong password and clears the field', async () => {
    const onSubmit = vi.fn().mockRejectedValue(new ApiError(401, 'x', 'INVALID_CREDENTIALS'));
    render(<AdminLoginForm onSubmit={onSubmit} />);

    type(/admin password/i, 'nope');
    fireEvent.click(screen.getByRole('button', { name: /log in/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/wrong password/i);
    expect(screen.getByLabelText(/admin password/i)).toHaveValue('');
  });
});
