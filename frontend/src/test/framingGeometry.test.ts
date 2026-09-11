import { describe, expect, it } from 'vitest';

import {
  baseAspectRatio,
  CORNERS,
  EDGES,
  coverScale,
  rectForRatio,
  resizeRect,
  type Rect,
} from '@/services/framingGeometry';
import type { Dimensions } from '@/types';

/** Floating-point-safe rect comparison (resizeRect chains +/- on fractions). */
function expectRectClose(actual: Rect, expected: Rect): void {
  expect(actual.x).toBeCloseTo(expected.x, 9);
  expect(actual.y).toBeCloseTo(expected.y, 9);
  expect(actual.w).toBeCloseTo(expected.w, 9);
  expect(actual.h).toBeCloseTo(expected.h, 9);
}

describe('CORNERS / EDGES', () => {
  it('lists the four corner and four edge handles', () => {
    expect(CORNERS).toEqual(['nw', 'ne', 'se', 'sw']);
    expect(EDGES).toEqual(['n', 'e', 's', 'w']);
  });
});

describe('baseAspectRatio', () => {
  const dims: Dimensions = { width: 200, height: 100 };

  it('uses width/height directly for an even number of quarter turns', () => {
    expect(baseAspectRatio(dims, 0)).toBe(2);
    expect(baseAspectRatio(dims, 2)).toBe(2);
  });

  it('swaps width/height for an odd number of quarter turns', () => {
    expect(baseAspectRatio(dims, 1)).toBe(0.5);
    expect(baseAspectRatio(dims, 3)).toBe(0.5);
  });
});

describe('coverScale', () => {
  it('is 1 when the image is not straightened', () => {
    expect(coverScale(0, 200, 100)).toBe(1);
  });

  it('grows with the straighten angle to keep the frame covered', () => {
    const scale = coverScale(15, 200, 100);
    expect(scale).toBeGreaterThan(1);
  });

  it('treats positive and negative angles the same (uses the magnitude)', () => {
    expect(coverScale(-15, 200, 100)).toBe(coverScale(15, 200, 100));
  });
});

describe('rectForRatio', () => {
  it('returns a null rect and ratioFrac for the "Free" (null) ratio', () => {
    expect(rectForRatio(null, 1.5)).toEqual({ ratioFrac: null, rect: null });
  });

  it('locks to the image\'s own ratio when displayRatio is 0 ("Original")', () => {
    const { ratioFrac, rect } = rectForRatio(0, 2);
    expect(ratioFrac).toBe(1);
    expect(rect).toEqual({ x: 0, y: 0, w: 1, h: 1 });
  });

  it('fits a wide crop (ratioFrac >= 1) full-width, centered vertically', () => {
    const { ratioFrac, rect } = rectForRatio(16 / 9, 1);
    expect(ratioFrac).toBeCloseTo(16 / 9);
    expect(rect?.w).toBe(1);
    expect(rect?.h).toBeCloseTo(9 / 16);
    expect(rect?.x).toBe(0);
    expect(rect?.y).toBeCloseTo((1 - 9 / 16) / 2);
  });

  it('fits a tall crop (ratioFrac < 1) full-height, centered horizontally', () => {
    const { ratioFrac, rect } = rectForRatio(1, 2);
    expect(ratioFrac).toBeCloseTo(0.5);
    expect(rect?.h).toBe(1);
    expect(rect?.w).toBeCloseTo(0.5);
    expect(rect?.y).toBe(0);
    expect(rect?.x).toBeCloseTo((1 - 0.5) / 2);
  });
});

describe('resizeRect - move', () => {
  it('translates the rect by dx/dy', () => {
    const start = { x: 0.2, y: 0.2, w: 0.3, h: 0.3 };
    expectRectClose(resizeRect('move', start, 0.1, -0.1, null), { x: 0.3, y: 0.1, w: 0.3, h: 0.3 });
  });

  it('clamps the move so the rect stays inside the frame', () => {
    const start = { x: 0.8, y: 0.8, w: 0.3, h: 0.3 };
    const rect = resizeRect('move', start, 1, 1, null);
    expectRectClose(rect, { x: 0.7, y: 0.7, w: 0.3, h: 0.3 });
  });

  it('clamps a negative move at the top-left edge', () => {
    const start = { x: 0.05, y: 0.05, w: 0.3, h: 0.3 };
    const rect = resizeRect('move', start, -1, -1, null);
    expectRectClose(rect, { x: 0, y: 0, w: 0.3, h: 0.3 });
  });
});

describe('resizeRect - single edge handles (unlocked ratio)', () => {
  const start = { x: 0.3, y: 0.3, w: 0.3, h: 0.3 };

  it('east: grows width only', () => {
    expectRectClose(resizeRect('e', start, 0.1, 0.5, null), { x: 0.3, y: 0.3, w: 0.4, h: 0.3 });
  });

  it('west: moves x and grows width', () => {
    expectRectClose(resizeRect('w', start, -0.1, 0.5, null), { x: 0.2, y: 0.3, w: 0.4, h: 0.3 });
  });

  it('south: grows height only', () => {
    expectRectClose(resizeRect('s', start, 0.5, 0.1, null), { x: 0.3, y: 0.3, w: 0.3, h: 0.4 });
  });

  it('north: moves y and grows height', () => {
    expectRectClose(resizeRect('n', start, 0.5, -0.1, null), { x: 0.3, y: 0.2, w: 0.3, h: 0.4 });
  });

  it('east: shrink is clamped to the minimum fraction', () => {
    const rect = resizeRect('e', start, -1, 0, null);
    expect(rect.w).toBeCloseTo(0.08);
  });

  it('south: growth is clamped to the frame edge', () => {
    const rect = resizeRect('s', start, 0, 1, null);
    expect(rect.h).toBeCloseTo(0.7);
  });

  it('does not enter the ratio-lock branch when only one axis handle is active, even with a ratio set', () => {
    // (east || west) true, (north || south) false -> short-circuits before the lock.
    const rect = resizeRect('e', start, 0.1, 0, 1.5);
    expectRectClose(rect, { x: 0.3, y: 0.3, w: 0.4, h: 0.3 });
  });

  it('does not enter the ratio-lock branch for a pure vertical handle, even with a ratio set', () => {
    // (north || south) true, (east || west) false -> short-circuits before the lock.
    const rect = resizeRect('s', start, 0, 0.1, 1.5);
    expectRectClose(rect, { x: 0.3, y: 0.3, w: 0.3, h: 0.4 });
  });
});

describe('resizeRect - corner handles, unlocked ratio', () => {
  it('se: grows width and height independently', () => {
    const start = { x: 0.3, y: 0.3, w: 0.3, h: 0.3 };
    expectRectClose(resizeRect('se', start, 0.1, 0.1, null), { x: 0.3, y: 0.3, w: 0.4, h: 0.4 });
  });

  it('nw: moves both x/y and grows width/height', () => {
    const start = { x: 0.3, y: 0.3, w: 0.3, h: 0.3 };
    expectRectClose(resizeRect('nw', start, -0.1, -0.1, null), { x: 0.2, y: 0.2, w: 0.4, h: 0.4 });
  });

  it('ne: moves y only, grows width and height', () => {
    const start = { x: 0.2, y: 0.5, w: 0.3, h: 0.3 };
    const rect = resizeRect('ne', start, 0.1, -0.1, null);
    expectRectClose(rect, { x: 0.2, y: 0.4, w: 0.4, h: 0.4 });
  });

  it('sw: moves x only, grows width and height', () => {
    const start = { x: 0.3, y: 0.3, w: 0.3, h: 0.3 };
    const rect = resizeRect('sw', start, -0.1, 0.1, null);
    expectRectClose(rect, { x: 0.2, y: 0.3, w: 0.4, h: 0.4 });
  });
});

describe('resizeRect - corner handles, ratio locked', () => {
  it('se (east+south): derives height from width, no capping needed', () => {
    const start = { x: 0.2, y: 0.2, w: 0.3, h: 0.3 };
    const rect = resizeRect('se', start, 0.1, 0.1, 2);
    expectRectClose(rect, { x: 0.2, y: 0.2, w: 0.4, h: 0.2 });
  });

  it('ne (east+north): re-derives the top edge from the new height, no capping needed', () => {
    const start = { x: 0.2, y: 0.5, w: 0.3, h: 0.3 };
    const rect = resizeRect('ne', start, 0.2, -0.1, 1);
    expectRectClose(rect, { x: 0.2, y: 0.3, w: 0.5, h: 0.5 });
  });

  it('nw (west+north): caps when the derived rect would go above the frame (y < 0)', () => {
    const start = { x: 0.5, y: 0.05, w: 0.2, h: 0.2 };
    const rect = resizeRect('nw', start, -0.3, -0.3, 1);
    expectRectClose(rect, { x: 0.45, y: 0, w: 0.25, h: 0.25 });
  });

  it('sw (west+south): caps when the derived rect would overflow the bottom (y + h > 1)', () => {
    const start = { x: 0.5, y: 0.85, w: 0.2, h: 0.1 };
    const rect = resizeRect('sw', start, -0.3, 0.3, 1);
    expectRectClose(rect, { x: 0.55, y: 0.85, w: 0.15, h: 0.15 });
  });
});
