import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ImagePreview } from '@/components/ImagePreview';

/** jsdom's default rect is all zeros; give the container real-ish bounds. */
function mockContainerRect(): void {
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue({
    x: 0,
    y: 0,
    left: 0,
    top: 0,
    width: 200,
    height: 100,
    right: 200,
    bottom: 100,
    toJSON: () => ({}),
  });
}

describe('ImagePreview', () => {
  it('steps the zoom level and clamps at the bounds', () => {
    render(<ImagePreview originalUrl="/a" processedUrl="/b" />);

    const zoomIn = screen.getByRole('button', { name: /zoom in/i });
    const zoomOut = screen.getByRole('button', { name: /zoom out/i });
    const reset = screen.getByRole('button', { name: /reset zoom/i });

    expect(reset).toHaveTextContent('100%');
    expect(zoomOut).toBeDisabled();

    fireEvent.click(zoomIn);
    expect(reset).toHaveTextContent('150%');

    for (let i = 0; i < 10; i += 1) {
      fireEvent.click(zoomIn);
    }
    expect(reset).toHaveTextContent('400%');
    expect(zoomIn).toBeDisabled();

    fireEvent.click(reset);
    expect(reset).toHaveTextContent('100%');
  });

  it('draws one circle per detected star when a mask overlay is given', () => {
    const { container } = render(
      <ImagePreview
        originalUrl="/a"
        processedUrl="/b"
        starMaskOverlay={[
          { x: 0.2, y: 0.3, radius: 0.02 },
          { x: 0.8, y: 0.7, radius: 0.03 },
        ]}
      />,
    );

    expect(container.querySelectorAll('svg circle')).toHaveLength(2);
  });

  it('renders no overlay circles without a mask', () => {
    const { container } = render(<ImagePreview originalUrl="/a" processedUrl="/b" />);
    expect(container.querySelectorAll('svg circle')).toHaveLength(0);
  });

  it('picks a focal point from a click while in picking mode, instead of dragging the divider', () => {
    mockContainerRect();
    const onFocalPointPick = vi.fn();
    const { container } = render(
      <ImagePreview
        originalUrl="/a"
        processedUrl="/b"
        pickingFocalPoint
        onFocalPointPick={onFocalPointPick}
      />,
    );

    const stage = container.querySelector('.cursor-crosshair')!;
    fireEvent.pointerDown(stage, { clientX: 50, clientY: 25 });

    expect(onFocalPointPick).toHaveBeenCalledWith({ x: 0.25, y: 0.25 });
  });

  it('shows a marker once a focal point is set, and lets it be cleared', () => {
    const onClearFocalPoint = vi.fn();
    const { container } = render(
      <ImagePreview
        originalUrl="/a"
        processedUrl="/b"
        focalPoint={{ x: 0.5, y: 0.5 }}
        onTogglePickFocalPoint={vi.fn()}
        onClearFocalPoint={onClearFocalPoint}
      />,
    );

    expect(container.querySelector('svg circle[r="7"]')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Clear focal point' }));
    expect(onClearFocalPoint).toHaveBeenCalledTimes(1);
  });

  it('toggles the focal-point button label between set/change/cancel', () => {
    const onToggle = vi.fn();
    const { rerender } = render(
      <ImagePreview originalUrl="/a" processedUrl="/b" onTogglePickFocalPoint={onToggle} />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Set focal point' }));
    expect(onToggle).toHaveBeenCalledTimes(1);

    rerender(
      <ImagePreview
        originalUrl="/a"
        processedUrl="/b"
        onTogglePickFocalPoint={onToggle}
        focalPoint={{ x: 0.5, y: 0.5 }}
      />,
    );
    expect(screen.getByRole('button', { name: 'Change focal point' })).toBeInTheDocument();

    rerender(
      <ImagePreview
        originalUrl="/a"
        processedUrl="/b"
        onTogglePickFocalPoint={onToggle}
        focalPoint={{ x: 0.5, y: 0.5 }}
        pickingFocalPoint
      />,
    );
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });
});
