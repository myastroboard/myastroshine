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
});
