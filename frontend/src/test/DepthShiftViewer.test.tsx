import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { DepthShiftViewer } from '@/components/DepthShiftViewer';

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
  } as DOMRect);
}

const layers = ['/layer-0.png', '/layer-1.png', '/layer-2.png'];

describe('DepthShiftViewer', () => {
  it('renders every depth layer image and the intensity readout', () => {
    render(
      <DepthShiftViewer
        depthLayerUrls={layers}
        intensity={40}
        onIntensityChange={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByRole('dialog', { name: 'Depth shift viewer' })).toBeInTheDocument();
    layers.forEach((url, index) => {
      const img = screen.getByAltText(`Depth layer ${index}`) as HTMLImageElement;
      expect(img).toHaveAttribute('src', url);
    });
    expect(screen.getByText('40%')).toBeInTheDocument();
  });

  it('calls onClose from the close button, the Escape key, and a backdrop click', () => {
    const onClose = vi.fn();
    render(
      <DepthShiftViewer
        depthLayerUrls={layers}
        intensity={0}
        onIntensityChange={vi.fn()}
        onClose={onClose}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(2);

    fireEvent.click(screen.getByRole('dialog'));
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it('ignores other keys and clicks inside the frame', () => {
    const onClose = vi.fn();
    render(
      <DepthShiftViewer
        depthLayerUrls={layers}
        intensity={0}
        onIntensityChange={vi.fn()}
        onClose={onClose}
      />,
    );

    fireEvent.keyDown(window, { key: 'Enter' });
    fireEvent.click(screen.getByAltText('Depth layer 0'));
    expect(onClose).not.toHaveBeenCalled();
  });

  it('reports a new intensity from the slider', () => {
    const onIntensityChange = vi.fn();
    render(
      <DepthShiftViewer
        depthLayerUrls={layers}
        intensity={20}
        onIntensityChange={onIntensityChange}
        onClose={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText('Depth shift intensity'), { target: { value: '75' } });
    expect(onIntensityChange).toHaveBeenCalledWith(75);
  });

  it('shifts far layers more than near layers as the pointer moves', () => {
    mockContainerRect();
    const { container } = render(
      <DepthShiftViewer
        depthLayerUrls={layers}
        intensity={100}
        onIntensityChange={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    const stage = container.querySelector('.overflow-hidden') as HTMLElement;
    // Centre of the 200x100 box is (100, 50); move to the right/bottom edge.
    fireEvent.mouseMove(stage, { clientX: 200, clientY: 100 });

    const images = container.querySelectorAll('img');
    // index 0 (farthest) moves most, the last layer (depthFactor closest to 1) least.
    const firstTransform = (images[0] as HTMLImageElement).style.transform;
    const lastTransform = (images[images.length - 1] as HTMLImageElement).style.transform;
    expect(firstTransform).not.toBe(lastTransform);
    expect(firstTransform).toBe('translate(25px, 25px)');
  });

  it('falls back to a 16:9 aspect ratio and no max-width by default', () => {
    const { container } = render(
      <DepthShiftViewer
        depthLayerUrls={layers}
        intensity={0}
        onIntensityChange={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    const stage = container.querySelector('.overflow-hidden') as HTMLElement;
    expect(stage.style.aspectRatio).toBe(`${16 / 9} / 1`);
    expect(stage.style.maxWidth).toBe('');
  });

  it('uses the given landscape aspect ratio with no max-width cap', () => {
    const { container } = render(
      <DepthShiftViewer
        depthLayerUrls={layers}
        intensity={0}
        aspectRatio={2}
        onIntensityChange={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    const stage = container.querySelector('.overflow-hidden') as HTMLElement;
    expect(stage.style.aspectRatio).toBe('2 / 1');
    expect(stage.style.maxWidth).toBe('');
  });

  it('caps the width for a portrait aspect ratio', () => {
    const { container } = render(
      <DepthShiftViewer
        depthLayerUrls={layers}
        intensity={0}
        aspectRatio={0.5}
        onIntensityChange={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    const stage = container.querySelector('.overflow-hidden') as HTMLElement;
    expect(stage.style.aspectRatio).toBe('0.5 / 1');
    expect(stage.style.maxWidth).toBe('calc(42.5vh)');
  });

  it('treats a non-positive aspect ratio as absent', () => {
    const { container } = render(
      <DepthShiftViewer
        depthLayerUrls={layers}
        intensity={0}
        aspectRatio={0}
        onIntensityChange={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    const stage = container.querySelector('.overflow-hidden') as HTMLElement;
    expect(stage.style.aspectRatio).toBe(`${16 / 9} / 1`);
  });
});
