import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ToneCurveEditor } from '@/components/ToneCurveEditor';

// jsdom implements pointer capture on HTMLElement but not on SVG elements
// (real browsers support it on any Element per the Pointer Events spec) - stub
// it so dragging a curve point doesn't throw in this test environment.
Element.prototype.setPointerCapture ??= vi.fn();
Element.prototype.releasePointerCapture ??= vi.fn();

/** jsdom's default rect is all zeros; a 255x255 box maps screen px 1:1 to the 0-255 domain. */
function mockGraphRect(): void {
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue({
    x: 0,
    y: 0,
    left: 0,
    top: 0,
    width: 255,
    height: 255,
    right: 255,
    bottom: 255,
    toJSON: () => ({}),
  });
}

describe('ToneCurveEditor', () => {
  it('does not clip control points sitting exactly at the graph edges', () => {
    // Regression: without `overflow-visible`, a point at y=0 or y=255 has half
    // its hit area clipped by the SVG viewBox boundary and becomes hard or
    // impossible to grab in a real browser (jsdom doesn't clip, so this only
    // guards the className, not the actual pixel-level symptom).
    render(<ToneCurveEditor points={[]} onChange={vi.fn()} />);
    const svg = screen.getByRole('img', { name: 'Tone curve' });
    expect(svg).toHaveClass('overflow-visible');
  });

  it('shows the default 2-point identity line when points is empty', () => {
    render(<ToneCurveEditor points={[]} onChange={vi.fn()} />);
    expect(screen.getAllByRole('img').length).toBeGreaterThanOrEqual(0);
    // Two circles: the default identity endpoints (0,0) and (255,255).
    const svg = screen.getByRole('img', { name: 'Tone curve' });
    expect(svg.querySelectorAll('circle')).toHaveLength(2);
  });

  it('dragging an endpoint reports a new y for that point only', () => {
    mockGraphRect();
    const onChange = vi.fn();
    render(<ToneCurveEditor points={[]} onChange={onChange} />);

    const svg = screen.getByRole('img', { name: 'Tone curve' });
    const circles = svg.querySelectorAll('circle');
    const firstPoint = circles[0]; // (0, 0) - screen bottom-left

    fireEvent.pointerDown(firstPoint, { clientX: 0, clientY: 255, pointerId: 1 });
    fireEvent.pointerMove(svg, { clientX: 0, clientY: 155, pointerId: 1 }); // drag up -> higher y
    fireEvent.pointerUp(svg, { pointerId: 1 });

    expect(onChange).toHaveBeenCalled();
    const lastCall = onChange.mock.calls.at(-1)?.[0];
    expect(lastCall[0]).toEqual({ x: 0, y: 100 });
    expect(lastCall[1]).toEqual({ x: 255, y: 255 });
  });

  it('double-clicking empty space adds a point', () => {
    mockGraphRect();
    const onChange = vi.fn();
    render(<ToneCurveEditor points={[]} onChange={onChange} />);

    const svg = screen.getByRole('img', { name: 'Tone curve' });
    fireEvent.doubleClick(svg, { clientX: 128, clientY: 105 }); // x=128, y=255-105=150

    expect(onChange).toHaveBeenCalledWith([
      { x: 0, y: 0 },
      { x: 128, y: 150 },
      { x: 255, y: 255 },
    ]);
  });

  it('double-clicking an interior point removes it, but endpoints are permanent', () => {
    const onChange = vi.fn();
    const points = [
      { x: 0, y: 0 },
      { x: 128, y: 150 },
      { x: 255, y: 255 },
    ];
    render(<ToneCurveEditor points={points} onChange={onChange} />);

    const svg = screen.getByRole('img', { name: 'Tone curve' });
    const circles = svg.querySelectorAll('circle');

    fireEvent.doubleClick(circles[0]); // first endpoint - must stay
    expect(onChange).not.toHaveBeenCalled();

    fireEvent.doubleClick(circles[1]); // interior point - removable
    expect(onChange).toHaveBeenCalledWith([
      { x: 0, y: 0 },
      { x: 255, y: 255 },
    ]);
  });

  it('the Reset button clears the curve back to identity', () => {
    const onChange = vi.fn();
    render(
      <ToneCurveEditor
        points={[
          { x: 0, y: 0 },
          { x: 128, y: 150 },
          { x: 255, y: 255 },
        ]}
        onChange={onChange}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Reset' }));
    expect(onChange).toHaveBeenCalledWith([]);
  });
});
