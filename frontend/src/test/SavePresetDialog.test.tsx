import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SavePresetDialog } from '@/components/SavePresetDialog';

describe('SavePresetDialog', () => {
  it('validates that a name is entered', () => {
    const onSave = vi.fn();
    render(<SavePresetDialog onSave={onSave} onClose={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(screen.getByText(/name is required/i)).toBeInTheDocument();
    expect(onSave).not.toHaveBeenCalled();
  });

  it('passes the trimmed name and description, then closes', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();
    render(<SavePresetDialog onSave={onSave} onClose={onClose} />);

    fireEvent.change(screen.getByPlaceholderText('My nebula look'), {
      target: { value: '  Deep sky  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(onSave).toHaveBeenCalledWith('Deep sky', '');
  });

  it('keeps the dialog open and shows the error when saving fails', async () => {
    const onSave = vi.fn().mockRejectedValue(new Error('Preset name already exists'));
    const onClose = vi.fn();
    render(<SavePresetDialog onSave={onSave} onClose={onClose} />);

    fireEvent.change(screen.getByPlaceholderText('My nebula look'), {
      target: { value: 'Nebula' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(screen.getByText(/already exists/i)).toBeInTheDocument();
    });
    expect(onClose).not.toHaveBeenCalled();
  });
});
