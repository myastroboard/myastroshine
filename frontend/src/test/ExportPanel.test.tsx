import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ExportPanel } from '@/components/ExportPanel';

const base = {
  onDownload: vi.fn(),
  onSendToAstroDex: vi.fn(),
  onSaveAsPreset: vi.fn(),
};

describe('ExportPanel', () => {
  it('hides the AstroDex button and its feedback outside an AstroDex session', () => {
    render(<ExportPanel {...base} astrodexSent astrodexError="boom" />);

    expect(screen.queryByRole('button', { name: /astrodex/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/Sent to AstroDex/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Could not send/)).not.toBeInTheDocument();
  });

  it('reports the send and shows a spinner label while sending', () => {
    const onSendToAstroDex = vi.fn();
    const { rerender } = render(
      <ExportPanel {...base} canSendToAstroDex onSendToAstroDex={onSendToAstroDex} />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Send to AstroDex' }));
    expect(onSendToAstroDex).toHaveBeenCalledTimes(1);

    rerender(<ExportPanel {...base} canSendToAstroDex astrodexSending />);
    expect(screen.getByRole('button', { name: 'Sending...' })).toBeDisabled();
  });

  it('confirms a successful send and surfaces a failure', () => {
    const { rerender } = render(<ExportPanel {...base} canSendToAstroDex astrodexSent />);
    expect(screen.getByText('Sent to AstroDex.')).toBeInTheDocument();

    rerender(<ExportPanel {...base} canSendToAstroDex astrodexError="AstroDex unreachable" />);
    expect(screen.getByText(/Could not send to AstroDex: AstroDex unreachable/)).toBeInTheDocument();
    expect(screen.queryByText('Sent to AstroDex.')).not.toBeInTheDocument();
  });
});
