import { describe, expect, it } from 'vitest';

import { curveToSvgPath } from '@/services/toneCurve';

describe('curveToSvgPath', () => {
  it('returns an empty string for fewer than 2 points', () => {
    expect(curveToSvgPath([])).toBe('');
    expect(curveToSvgPath([{ x: 0, y: 0 }])).toBe('');
  });

  it('starts the path at the first point', () => {
    const d = curveToSvgPath([
      { x: 0, y: 0 },
      { x: 255, y: 255 },
    ]);
    expect(d.startsWith('M 0 0')).toBe(true);
  });

  it('emits one cubic segment per pair of adjacent points', () => {
    const d = curveToSvgPath([
      { x: 0, y: 0 },
      { x: 128, y: 150 },
      { x: 255, y: 255 },
    ]);
    expect(d.match(/C /g)).toHaveLength(2);
  });

  it('ends the last segment exactly at the last point', () => {
    const d = curveToSvgPath([
      { x: 0, y: 10 },
      { x: 255, y: 200 },
    ]);
    expect(d.trim().endsWith('255 200')).toBe(true);
  });

  it('flattens the tangents around a flat (zero-delta) segment', () => {
    // The middle segment (100,50)->(200,50) has delta 0: both its tangents
    // must collapse to 0, so the Bezier control points sit exactly on the
    // flat endpoints instead of overshooting.
    const d = curveToSvgPath([
      { x: 0, y: 0 },
      { x: 100, y: 50 },
      { x: 200, y: 50 },
      { x: 255, y: 255 },
    ]);
    const segments = d.split(/(?=[MC] )/).map((s) => s.trim());
    // Segment for 100,50 -> 200,50: "C c1x 50, c2x 50, 200 50"
    expect(segments[2]).toMatch(/^C \d+(\.\d+)? 50, \d+(\.\d+)? 50, 200 50$/);
  });

  it('clamps overshooting tangents when the monotone magnitude limit is exceeded', () => {
    // A steep-then-shallow-then-steep run drives alpha/beta past the
    // Fritsch-Carlson limit for the middle segment, exercising the scale-down.
    const points = [
      { x: 0, y: 0 },
      { x: 1, y: 10 },
      { x: 2, y: 10.5 },
      { x: 3, y: 20 },
    ];
    expect(() => curveToSvgPath(points)).not.toThrow();
    const d = curveToSvgPath(points);
    expect(d.match(/C /g)).toHaveLength(3);
  });
});
