import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ImagePreview } from '@/components/ImagePreview';

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
});
