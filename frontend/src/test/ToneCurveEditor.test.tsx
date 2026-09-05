import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ToneCurveEditor } from '@/components/ToneCurveEditor';
import type { CurvePoint } from '@/types';

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

const EMPTY_CURVES = { rgb: [], red: [], green: [], blue: [] };

function curvesWith(rgb: CurvePoint[]) {
  return { rgb, red: [], green: [], blue: [] };
}

describe('ToneCurveEditor', () => {
  it('does not clip control points sitting exactly at the graph edges', () => {
    // Regression: without `overflow-visible`, a point at y=0 or y=255 has half
    // its hit area clipped by the SVG viewBox boundary and becomes hard or
    // impossible to grab in a real browser (jsdom doesn't clip, so this only
    // guards the className, not the actual pixel-level symptom).
    render(<ToneCurveEditor curves={EMPTY_CURVES} onChange={vi.fn()} />);
    const svg = screen.getByRole('img', { name: 'Tone curve' });
    expect(svg).toHaveClass('overflow-visible');
  });

  it('shows the default 2-point identity line when the active channel is empty', () => {
    render(<ToneCurveEditor curves={EMPTY_CURVES} onChange={vi.fn()} />);
    // Two circles: the default identity endpoints (0,0) and (255,255).
    const svg = screen.getByRole('img', { name: 'Tone curve' });
    expect(svg.querySelectorAll('circle')).toHaveLength(2);
  });

  it('dragging an endpoint reports a new y for the active (rgb) channel only', () => {
    mockGraphRect();
    const onChange = vi.fn();
    render(<ToneCurveEditor curves={EMPTY_CURVES} onChange={onChange} />);

    const svg = screen.getByRole('img', { name: 'Tone curve' });
    const circles = svg.querySelectorAll('circle');
    const firstPoint = circles[0]; // (0, 0) - screen bottom-left

    fireEvent.pointerDown(firstPoint, { clientX: 0, clientY: 255, pointerId: 1 });
    fireEvent.pointerMove(svg, { clientX: 0, clientY: 155, pointerId: 1 }); // drag up -> higher y
    fireEvent.pointerUp(svg, { pointerId: 1 });

    expect(onChange).toHaveBeenCalled();
    const [channel, points] = onChange.mock.calls.at(-1) as [string, CurvePoint[]];
    expect(channel).toBe('rgb');
    expect(points[0]).toEqual({ x: 0, y: 100 });
    expect(points[1]).toEqual({ x: 255, y: 255 });
  });

  it('double-clicking empty space adds a point to the active channel', () => {
    mockGraphRect();
    const onChange = vi.fn();
    render(<ToneCurveEditor curves={EMPTY_CURVES} onChange={onChange} />);

    const svg = screen.getByRole('img', { name: 'Tone curve' });
    fireEvent.doubleClick(svg, { clientX: 128, clientY: 105 }); // x=128, y=255-105=150

    expect(onChange).toHaveBeenCalledWith('rgb', [
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
    render(<ToneCurveEditor curves={curvesWith(points)} onChange={onChange} />);

    const svg = screen.getByRole('img', { name: 'Tone curve' });
    const circles = svg.querySelectorAll('circle');

    fireEvent.doubleClick(circles[0]); // first endpoint - must stay
    expect(onChange).not.toHaveBeenCalled();

    fireEvent.doubleClick(circles[1]); // interior point - removable
    expect(onChange).toHaveBeenCalledWith('rgb', [
      { x: 0, y: 0 },
      { x: 255, y: 255 },
    ]);
  });

  it('the Reset button clears the active channel back to identity', () => {
    const onChange = vi.fn();
    const points = [
      { x: 0, y: 0 },
      { x: 128, y: 150 },
      { x: 255, y: 255 },
    ];
    render(<ToneCurveEditor curves={curvesWith(points)} onChange={onChange} />);

    fireEvent.click(screen.getByRole('button', { name: 'Reset' }));
    expect(onChange).toHaveBeenCalledWith('rgb', []);
  });

  it('switching channel tabs edits and reports that channel independently', () => {
    const onChange = vi.fn();
    const curves = {
      rgb: [],
      red: [
        { x: 0, y: 0 },
        { x: 255, y: 255 },
      ],
      green: [],
      blue: [],
    };
    render(<ToneCurveEditor curves={curves} onChange={onChange} />);

    fireEvent.click(screen.getByRole('tab', { name: 'Red' }));
    fireEvent.click(screen.getByRole('button', { name: 'Reset' }));

    expect(onChange).toHaveBeenCalledWith('red', []);
  });
});
