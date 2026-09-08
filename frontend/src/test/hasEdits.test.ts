import { describe, expect, it } from 'vitest';

import { DEFAULT_GEOMETRY, DEFAULT_PARAMETERS, hasEdits } from '@/types';

describe('hasEdits', () => {
  it('is false for the untouched default parameters', () => {
    expect(hasEdits(DEFAULT_PARAMETERS)).toBe(false);
  });

  it('is true when a slider parameter moved', () => {
    expect(hasEdits({ ...DEFAULT_PARAMETERS, contrast: 1.4 })).toBe(true);
  });

  it('is true when star removal is engaged', () => {
    expect(hasEdits({ ...DEFAULT_PARAMETERS, starRemoval: 80 })).toBe(true);
  });

  it('is true when the framing changed', () => {
    expect(
      hasEdits({ ...DEFAULT_PARAMETERS, geometry: { ...DEFAULT_GEOMETRY, rotateQuarters: 1 } }),
    ).toBe(true);
  });

  it('is true when a tone curve has points', () => {
    expect(
      hasEdits({
        ...DEFAULT_PARAMETERS,
        curvePoints: [
          { x: 0, y: 0 },
          { x: 255, y: 255 },
        ],
      }),
    ).toBe(true);
  });
});
