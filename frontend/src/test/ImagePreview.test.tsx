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
});
