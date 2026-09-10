import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ExportPanel } from '@/components/ExportPanel';

const base = {
  defaultFilename: 'orion_myastroshine',
  onDownload: vi.fn(),
  onReturnToAstroDex: vi.fn(),
  onSaveAsPreset: vi.fn(),
};

describe('ExportPanel', () => {
  it('seeds the filename field and downloads with the edited name', () => {
    const onDownload = vi.fn();
    render(<ExportPanel {...base} onDownload={onDownload} />);

    const field = screen.getByLabelText('File name');
    expect(field).toHaveValue('orion_myastroshine');

    fireEvent.change(field, { target: { value: 'orion final' } });
    fireEvent.click(screen.getByRole('button', { name: 'Download' }));
    expect(onDownload).toHaveBeenCalledWith('orion final');
  });

  it('disables Download when the filename field is blank', () => {
    render(<ExportPanel {...base} defaultFilename="" />);

    expect(screen.getByRole('button', { name: 'Download' })).toBeDisabled();
  });

  it('hides the AstroDex button and its feedback outside an AstroDex session', () => {
    render(<ExportPanel {...base} astrodexReturned astrodexError="boom" />);

    expect(screen.queryByRole('button', { name: /astrodex/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/Added to the AstroDex/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Could not send back/)).not.toBeInTheDocument();
  });

  it('reports the return and shows a spinner label while sending', () => {
    const onReturnToAstroDex = vi.fn();
    const { rerender } = render(
      <ExportPanel {...base} canReturnToAstroDex onReturnToAstroDex={onReturnToAstroDex} />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Send back to AstroDex' }));
    expect(onReturnToAstroDex).toHaveBeenCalledTimes(1);

    rerender(<ExportPanel {...base} canReturnToAstroDex astrodexReturning />);
    expect(screen.getByRole('button', { name: 'Sending...' })).toBeDisabled();
  });

  it('confirms a successful return and surfaces a failure', () => {
    const { rerender } = render(<ExportPanel {...base} canReturnToAstroDex astrodexReturned />);
    expect(screen.getByText('Added to the AstroDex object as a new picture.')).toBeInTheDocument();

    rerender(
      <ExportPanel {...base} canReturnToAstroDex astrodexError="AstroDex unreachable" />,
    );
    expect(
      screen.getByText(/Could not send back to AstroDex: AstroDex unreachable/),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('Added to the AstroDex object as a new picture.'),
    ).not.toBeInTheDocument();
  });
});
