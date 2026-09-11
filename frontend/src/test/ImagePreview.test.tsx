import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ImagePreview } from '@/components/ImagePreview';
import { DEFAULT_GEOMETRY } from '@/types';

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

  it('keeps the before/after divider under the pointer when zoomed', () => {
    mockContainerRect();
    const { container } = render(<ImagePreview originalUrl="/a" processedUrl="/b" />);

    // Zoom to 200%, then drag the split to 75% of the container width.
    fireEvent.click(screen.getByRole('button', { name: /zoom in/i }));
    fireEvent.click(screen.getByRole('button', { name: /zoom in/i }));

    const stage = container.querySelector('.cursor-ew-resize')!;
    fireEvent.pointerDown(stage, { clientX: 150, clientY: 50, pointerId: 1 });

    // The images are scaled about the centre, so the divider element sits back
    // at the container fraction the pointer was actually over (75%).
    const divider = container.querySelector('.bg-white\\/70') as HTMLElement;
    expect(divider.style.left).toBe('75%');
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

  it('shows a marker once a focal point is set', () => {
    const { container } = render(
      <ImagePreview originalUrl="/a" processedUrl="/b" focalPoint={{ x: 0.5, y: 0.5 }} />,
    );

    expect(container.querySelector('svg circle[r="7"]')).toBeInTheDocument();
  });

  it('shows the crop frame instead of the before/after view while framing', () => {
    render(
      <ImagePreview
        originalUrl="/a"
        processedUrl="/b"
        framing={{
          imageUrl: '/source',
          dimensions: { width: 4000, height: 3000 },
          geometry: DEFAULT_GEOMETRY,
          ratioFrac: null,
          onGeometryChange: vi.fn(),
        }}
      />,
    );

    expect(screen.getByAltText('Crop source')).toBeInTheDocument();
    expect(screen.queryByAltText('Processed')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /zoom in/i })).not.toBeInTheDocument();
  });

  it('reports a crop-rectangle drag as a geometry change while framing', () => {
    mockContainerRect();
    const onGeometryChange = vi.fn();
    const { container } = render(
      <ImagePreview
        originalUrl="/a"
        processedUrl="/b"
        framing={{
          imageUrl: '/source',
          dimensions: { width: 4000, height: 3000 },
          geometry: DEFAULT_GEOMETRY,
          ratioFrac: null,
          onGeometryChange,
        }}
      />,
    );

    const frame = container.querySelector('.cursor-move')!;
    fireEvent.pointerDown(frame, { clientX: 100, clientY: 50, pointerId: 1 });
    fireEvent.pointerMove(frame, { clientX: 120, clientY: 50, pointerId: 1 });

    expect(onGeometryChange).toHaveBeenCalled();
  });

  it('drags the divider across multiple pointer moves and stops on pointer up', () => {
    mockContainerRect();
    const { container } = render(<ImagePreview originalUrl="/a" processedUrl="/b" />);

    const stage = container.querySelector('.cursor-ew-resize')!;
    fireEvent.pointerDown(stage, { clientX: 50, clientY: 50, pointerId: 1 });

    const divider = container.querySelector('.bg-white\\/70') as HTMLElement;
    expect(divider.style.left).toBe('25%');
    // While dragging, the handle grows (scale-110).
    expect(divider.querySelector('span')).toHaveClass('scale-110');

    fireEvent.pointerMove(stage, { clientX: 150, clientY: 50, pointerId: 1 });
    expect(divider.style.left).toBe('75%');

    fireEvent.pointerUp(stage, { pointerId: 1 });
    expect(divider.querySelector('span')).not.toHaveClass('scale-110');

    // Once released, further pointer moves no longer affect the split.
    fireEvent.pointerMove(stage, { clientX: 0, clientY: 50, pointerId: 1 });
    expect(divider.style.left).toBe('75%');
  });

  it('ends the drag on pointer cancel too', () => {
    mockContainerRect();
    const { container } = render(<ImagePreview originalUrl="/a" processedUrl="/b" />);

    const stage = container.querySelector('.cursor-ew-resize')!;
    fireEvent.pointerDown(stage, { clientX: 50, clientY: 50, pointerId: 1 });
    const divider = container.querySelector('.bg-white\\/70') as HTMLElement;
    expect(divider.querySelector('span')).toHaveClass('scale-110');

    fireEvent.pointerCancel(stage, { pointerId: 1 });
    expect(divider.querySelector('span')).not.toHaveClass('scale-110');
  });

  it('does nothing when picking a focal point without a handler', () => {
    mockContainerRect();
    const { container } = render(
      <ImagePreview originalUrl="/a" processedUrl="/b" pickingFocalPoint />,
    );

    const stage = container.querySelector('.cursor-crosshair')!;
    expect(() => fireEvent.pointerDown(stage, { clientX: 50, clientY: 25 })).not.toThrow();
  });

  it('shows the picking-focal-point hint banner', () => {
    render(<ImagePreview originalUrl="/a" processedUrl="/b" pickingFocalPoint />);
    expect(screen.getByText(/click.*focal point/i)).toBeInTheDocument();
  });

  it('treats an explicit empty star mask overlay the same as no overlay', () => {
    const { container } = render(
      <ImagePreview originalUrl="/a" processedUrl="/b" starMaskOverlay={[]} />,
    );
    expect(container.querySelectorAll('svg circle')).toHaveLength(0);
  });

  it('renders the histogram panel when data is supplied', () => {
    const { container } = render(
      <ImagePreview
        originalUrl="/a"
        processedUrl="/b"
        histogram={{ r: [1, 2], g: [1, 2], b: [1, 2] }}
      />,
    );
    expect(container.querySelector('.panel-inset')).toBeInTheDocument();
  });

  it('uses an explicit aspect ratio when given', () => {
    const { container } = render(
      <ImagePreview originalUrl="/a" processedUrl="/b" aspectRatio={1.5} />,
    );
    const stage = container.querySelector('.cursor-ew-resize') as HTMLElement;
    expect(stage.style.aspectRatio).toBe('1.5 / 1');
    expect(stage.style.maxWidth).toBe('100%');
  });

  it('caps the width of a portrait frame instead of letterboxing', () => {
    const { container } = render(
      <ImagePreview originalUrl="/a" processedUrl="/b" aspectRatio={0.5} />,
    );
    const stage = container.querySelector('.cursor-ew-resize') as HTMLElement;
    expect(stage.style.aspectRatio).toBe('0.5 / 1');
    // jsdom's CSS parser folds the constant multiplication.
    expect(stage.style.maxWidth).toBe('calc(35vh)');
  });

  it('falls back to the processed image natural ratio once it loads', () => {
    const { container } = render(<ImagePreview originalUrl="/a" processedUrl="/b" />);
    const processedImg = screen.getByAltText('Processed') as HTMLImageElement;

    Object.defineProperty(processedImg, 'naturalWidth', { value: 800, configurable: true });
    Object.defineProperty(processedImg, 'naturalHeight', { value: 400, configurable: true });
    fireEvent.load(processedImg);

    const stage = container.querySelector('.cursor-ew-resize') as HTMLElement;
    expect(stage.style.aspectRatio).toBe('2 / 1');
  });

  it('ignores a zero-size natural image load', () => {
    const { container } = render(<ImagePreview originalUrl="/a" processedUrl="/b" />);
    const processedImg = screen.getByAltText('Processed') as HTMLImageElement;

    fireEvent.load(processedImg); // jsdom defaults naturalWidth/Height to 0

    const stage = container.querySelector('.cursor-ew-resize') as HTMLElement;
    expect(stage.style.aspectRatio).toBe(`${16 / 9} / 1`);
  });

  it('stops a pointer-down on the zoom controls from starting a divider drag', () => {
    mockContainerRect();
    const { container } = render(<ImagePreview originalUrl="/a" processedUrl="/b" />);

    const controls = container.querySelector('.cursor-default') as HTMLElement;
    fireEvent.pointerDown(controls, { clientX: 100, clientY: 50, pointerId: 1, bubbles: true });

    const divider = container.querySelector('.bg-white\\/70') as HTMLElement;
    expect(divider.querySelector('span')).not.toHaveClass('scale-110');
  });

  it('shows a determinate progress bar and a custom label while a long pass runs', () => {
    const { rerender } = render(
      <ImagePreview originalUrl="/a" processedUrl="/b" isLoading progress={0} />,
    );
    // No bar at 0 (a fast edit that never reports intermediate progress).
    expect(screen.queryByRole('progressbar')).toBeNull();
    expect(screen.getByText('Processing')).toBeInTheDocument();

    rerender(
      <ImagePreview
        originalUrl="/a"
        processedUrl="/b"
        isLoading
        progress={45}
        progressLabel="Removing stars (StarNet2)"
      />,
    );
    expect(screen.getByText('Removing stars (StarNet2)')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '45');
  });
});
