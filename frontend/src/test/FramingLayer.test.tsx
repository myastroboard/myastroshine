import { fireEvent, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { FramingLayer } from '@/components/FramingLayer';
import { DEFAULT_GEOMETRY } from '@/types';
import type { Dimensions, GeometryParameters } from '@/types';

const dimensions: Dimensions = { width: 4000, height: 3000 };

/** jsdom's default rect is all zeros; give the stage real-ish bounds. */
function mockStageRect(): void {
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

const smallCrop: GeometryParameters = {
  ...DEFAULT_GEOMETRY,
  cropX: 0.2,
  cropY: 0.2,
  cropW: 0.4,
  cropH: 0.4,
};

describe('FramingLayer', () => {
  it('renders the crop source image and a free-form frame with corners and edges', () => {
    const { container } = render(
      <FramingLayer
        imageUrl="/source.png"
        dimensions={dimensions}
        geometry={DEFAULT_GEOMETRY}
        ratioFrac={null}
        onGeometryChange={vi.fn()}
      />,
    );

    expect(container.querySelector('img')).toHaveAttribute('src', '/source.png');
    expect(container.querySelector('.cursor-move')).toBeInTheDocument();
    // 4 corner handles + 4 edge handles when the ratio isn't locked.
    expect(container.querySelectorAll('.cursor-nwse-resize, .cursor-nesw-resize')).toHaveLength(4);
    expect(container.querySelectorAll('.cursor-ns-resize, .cursor-ew-resize')).toHaveLength(4);
  });

  it('hides the edge handles once a ratio lock is active, keeping the corners', () => {
    const { container } = render(
      <FramingLayer
        imageUrl="/source.png"
        dimensions={dimensions}
        geometry={DEFAULT_GEOMETRY}
        ratioFrac={1}
        onGeometryChange={vi.fn()}
      />,
    );

    expect(container.querySelectorAll('.cursor-nwse-resize, .cursor-nesw-resize')).toHaveLength(4);
    expect(container.querySelectorAll('.cursor-ns-resize, .cursor-ew-resize')).toHaveLength(0);
  });

  it('drags the whole frame from a pointer-down/move on the body', () => {
    mockStageRect();
    const onGeometryChange = vi.fn();
    const { container } = render(
      <FramingLayer
        imageUrl="/source.png"
        dimensions={dimensions}
        geometry={smallCrop}
        ratioFrac={null}
        onGeometryChange={onGeometryChange}
      />,
    );

    const body = container.querySelector('.cursor-move') as HTMLElement;
    fireEvent.pointerDown(body, { clientX: 100, clientY: 50, pointerId: 1 });
    fireEvent.pointerMove(body, { clientX: 140, clientY: 50, pointerId: 1 });

    // dx = 40/200 = 0.2 -> x clamps to 0.4; y unchanged at 0.2.
    expect(onGeometryChange).toHaveBeenCalledWith({
      ...smallCrop,
      cropX: 0.4,
      cropY: 0.2,
      cropW: 0.4,
      cropH: 0.4,
    });
  });

  it('resizes from a corner handle', () => {
    mockStageRect();
    const onGeometryChange = vi.fn();
    const { container } = render(
      <FramingLayer
        imageUrl="/source.png"
        dimensions={dimensions}
        geometry={smallCrop}
        ratioFrac={null}
        onGeometryChange={onGeometryChange}
      />,
    );

    const se = container.querySelector('.right-0.bottom-0.cursor-nwse-resize') as HTMLElement;
    fireEvent.pointerDown(se, { clientX: 100, clientY: 50, pointerId: 1 });
    fireEvent.pointerMove(se, { clientX: 120, clientY: 50, pointerId: 1 });

    expect(onGeometryChange).toHaveBeenCalledTimes(1);
    const next = onGeometryChange.mock.calls[0][0] as GeometryParameters;
    expect(next.cropW).toBeCloseTo(0.5);
    expect(next.cropH).toBe(0.4);
  });

  it('does nothing on pointer move before any drag has started', () => {
    mockStageRect();
    const onGeometryChange = vi.fn();
    const { container } = render(
      <FramingLayer
        imageUrl="/source.png"
        dimensions={dimensions}
        geometry={smallCrop}
        ratioFrac={null}
        onGeometryChange={onGeometryChange}
      />,
    );

    const stage = container.firstChild as HTMLElement;
    fireEvent.pointerMove(stage, { clientX: 140, clientY: 50, pointerId: 1 });

    expect(onGeometryChange).not.toHaveBeenCalled();
  });

  it('stops updating once the drag ends on pointer up', () => {
    mockStageRect();
    const onGeometryChange = vi.fn();
    const { container } = render(
      <FramingLayer
        imageUrl="/source.png"
        dimensions={dimensions}
        geometry={smallCrop}
        ratioFrac={null}
        onGeometryChange={onGeometryChange}
      />,
    );

    const body = container.querySelector('.cursor-move') as HTMLElement;
    fireEvent.pointerDown(body, { clientX: 100, clientY: 50, pointerId: 1 });
    fireEvent.pointerUp(body, { clientX: 140, clientY: 50, pointerId: 1 });
    onGeometryChange.mockClear();

    fireEvent.pointerMove(body, { clientX: 180, clientY: 50, pointerId: 1 });
    expect(onGeometryChange).not.toHaveBeenCalled();
  });

  it('stops updating once the drag ends on pointer cancel', () => {
    mockStageRect();
    const onGeometryChange = vi.fn();
    const { container } = render(
      <FramingLayer
        imageUrl="/source.png"
        dimensions={dimensions}
        geometry={smallCrop}
        ratioFrac={null}
        onGeometryChange={onGeometryChange}
      />,
    );

    const body = container.querySelector('.cursor-move') as HTMLElement;
    fireEvent.pointerDown(body, { clientX: 100, clientY: 50, pointerId: 1 });
    fireEvent.pointerCancel(body, { clientX: 140, clientY: 50, pointerId: 1 });
    onGeometryChange.mockClear();

    fireEvent.pointerMove(body, { clientX: 180, clientY: 50, pointerId: 1 });
    expect(onGeometryChange).not.toHaveBeenCalled();
  });

  it('swaps the image box dimensions and covers the frame for an odd quarter turn', () => {
    const { container } = render(
      <FramingLayer
        imageUrl="/source.png"
        dimensions={dimensions}
        geometry={{ ...DEFAULT_GEOMETRY, rotateQuarters: 1 }}
        ratioFrac={null}
        onGeometryChange={vi.fn()}
      />,
    );

    const img = container.querySelector('img') as HTMLImageElement;
    // odd turn: baseW/baseH swap to dimensions.height/width (3000/4000).
    expect(img.style.width).toBe(`${(4000 / 3000) * 100}%`);
    expect(img.style.height).toBe(`${(3000 / 4000) * 100}%`);
  });

  it('flips the preview horizontally and vertically via the transform', () => {
    const { container } = render(
      <FramingLayer
        imageUrl="/source.png"
        dimensions={dimensions}
        geometry={{ ...DEFAULT_GEOMETRY, flipHorizontal: true, flipVertical: true }}
        ratioFrac={null}
        onGeometryChange={vi.fn()}
      />,
    );

    const img = container.querySelector('img') as HTMLImageElement;
    expect(img.style.transform).toContain('scaleX(-1)');
    expect(img.style.transform).toContain('scaleY(-1)');
  });
});
