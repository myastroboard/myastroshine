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
});
