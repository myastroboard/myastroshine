import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { StackFrameGrid } from '@/components/stacking/StackFrameGrid';
import type { PendingFrame } from '@/hooks/useStackProcessing';
import type { StackFrameInfo } from '@/types';

function pendingFrame(id: string, name: string): PendingFrame {
  return { id, name, sizeBytes: 10, file: new File([], name) };
}

function uploadedFrame(index: number, overrides: Partial<StackFrameInfo> = {}): StackFrameInfo {
  return {
    index,
    thumbUrl: `/thumb/${index}`,
    excluded: false,
    quality: null,
    ...overrides,
  };
}

describe('StackFrameGrid', () => {
  it('renders nothing when there are no pending or uploaded frames', () => {
    const { container } = render(
      <StackFrameGrid
        pending={[]}
        uploaded={[]}
        selected={null}
        interactive={false}
        onRemovePending={vi.fn()}
        onSelect={vi.fn()}
        onToggleExclude={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('lists pending frames and removes one on click', () => {
    const onRemovePending = vi.fn();
    render(
      <StackFrameGrid
        pending={[pendingFrame('p1', 'light1.fits'), pendingFrame('p2', 'light2.fits')]}
        uploaded={[]}
        selected={null}
        interactive={false}
        onRemovePending={onRemovePending}
        onSelect={vi.fn()}
        onToggleExclude={vi.fn()}
      />,
    );

    expect(screen.getByText('light1.fits')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /remove light2.fits/i }));
    expect(onRemovePending).toHaveBeenCalledWith('p2');
  });

  it('renders an uploaded frame without a quality badge and selects it on click', () => {
    const onSelect = vi.fn();
    render(
      <StackFrameGrid
        pending={[]}
        uploaded={[uploadedFrame(0)]}
        selected={null}
        interactive
        onRemovePending={vi.fn()}
        onSelect={onSelect}
        onToggleExclude={vi.fn()}
      />,
    );

    const frameButton = screen.getByRole('button', { name: /frame 1/i });
    expect(frameButton).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(frameButton);
    expect(onSelect).toHaveBeenCalledWith(0);
  });

  it('marks the selected frame and shows an accepted quality score badge', () => {
    render(
      <StackFrameGrid
        pending={[]}
        uploaded={[
          uploadedFrame(0, {
            quality: {
              starCount: 150,
              fwhm: 2.4,
              roundness: 0.95,
              background: 0.02,
              snr: 35,
              score: 91.4,
              weight: 1,
              accepted: true,
              rejectReason: null,
            },
          }),
        ]}
        selected={0}
        interactive
        onRemovePending={vi.fn()}
        onSelect={vi.fn()}
        onToggleExclude={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: /frame 1/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByText('91')).toBeInTheDocument();
  });

  it('shows a reject-reason badge and danger styling for an auto-rejected frame', () => {
    render(
      <StackFrameGrid
        pending={[]}
        uploaded={[
          uploadedFrame(2, {
            excluded: true,
            quality: {
              starCount: 10,
              fwhm: 7,
              roundness: 0.5,
              background: 0.2,
              snr: 5,
              score: 12,
              weight: 0,
              accepted: false,
              rejectReason: 'trailed',
            },
          }),
        ]}
        selected={null}
        interactive
        onRemovePending={vi.fn()}
        onSelect={vi.fn()}
        onToggleExclude={vi.fn()}
      />,
    );

    expect(screen.getByText('trailed')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /frame 3/i }).className).toContain('border-danger');
  });

  it('falls back to the generic reject label when no reason is given', () => {
    render(
      <StackFrameGrid
        pending={[]}
        uploaded={[
          uploadedFrame(0, {
            quality: {
              starCount: 10,
              fwhm: 7,
              roundness: 0.5,
              background: 0.2,
              snr: 5,
              score: 12,
              weight: 0,
              accepted: false,
              rejectReason: null,
            },
          }),
        ]}
        selected={null}
        interactive
        onRemovePending={vi.fn()}
        onSelect={vi.fn()}
        onToggleExclude={vi.fn()}
      />,
    );

    expect(screen.getByText('rejected')).toBeInTheDocument();
  });

  it('toggles exclusion via the checkbox and disables it when not interactive', () => {
    const onToggleExclude = vi.fn();
    const { rerender } = render(
      <StackFrameGrid
        pending={[]}
        uploaded={[uploadedFrame(0)]}
        selected={null}
        interactive
        onRemovePending={vi.fn()}
        onSelect={vi.fn()}
        onToggleExclude={onToggleExclude}
      />,
    );

    const checkbox = screen.getByRole('checkbox');
    expect(checkbox).not.toBeDisabled();
    fireEvent.click(checkbox);
    expect(onToggleExclude).toHaveBeenCalledWith(0, true);

    rerender(
      <StackFrameGrid
        pending={[]}
        uploaded={[uploadedFrame(0)]}
        selected={null}
        interactive={false}
        onRemovePending={vi.fn()}
        onSelect={vi.fn()}
        onToggleExclude={onToggleExclude}
      />,
    );
    expect(screen.getByRole('checkbox')).toBeDisabled();
  });

  it('dims an excluded frame thumbnail', () => {
    render(
      <StackFrameGrid
        pending={[]}
        uploaded={[uploadedFrame(0, { excluded: true })]}
        selected={null}
        interactive
        onRemovePending={vi.fn()}
        onSelect={vi.fn()}
        onToggleExclude={vi.fn()}
      />,
    );

    const img = document.querySelector('img');
    expect(img?.className).toContain('opacity-40');
  });
});
