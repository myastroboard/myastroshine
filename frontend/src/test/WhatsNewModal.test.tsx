import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { WhatsNewModal } from '@/components/WhatsNewModal';

const NOTES = '### Added\n\n- A new **bold** feature.\n- A [link](https://example.test).';

describe('WhatsNewModal', () => {
  it('renders markdown as real elements, not literal syntax', () => {
    render(
      <WhatsNewModal
        releaseName="v2.0.0"
        releaseNotes={NOTES}
        releaseUrl="https://example.test/release"
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Added', level: 3 })).toBeInTheDocument();
    expect(screen.getByText('bold').tagName).toBe('STRONG');
    const link = screen.getByRole('link', { name: 'link' });
    expect(link).toHaveAttribute('href', 'https://example.test');
    expect(screen.queryByText(/###/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\*\*/)).not.toBeInTheDocument();
  });

  it('closes on the Close button and on Escape', () => {
    const onClose = vi.fn();
    render(
      <WhatsNewModal releaseName="v2.0.0" releaseNotes={NOTES} releaseUrl={null} onClose={onClose} />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('ignores a non-Escape key press', () => {
    const onClose = vi.fn();
    render(
      <WhatsNewModal releaseName="v2.0.0" releaseNotes={NOTES} releaseUrl={null} onClose={onClose} />,
    );

    fireEvent.keyDown(window, { key: 'Enter' });

    expect(onClose).not.toHaveBeenCalled();
  });

  it('closes when the backdrop itself is clicked, but not when the dialog content is', () => {
    const onClose = vi.fn();
    render(
      <WhatsNewModal releaseName="v2.0.0" releaseNotes={NOTES} releaseUrl={null} onClose={onClose} />,
    );

    // Clicking inside the dialog panel (the event target is a descendant, not
    // the backdrop itself) must not close it.
    fireEvent.click(screen.getByRole('heading', { name: 'v2.0.0' }));
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('dialog'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
