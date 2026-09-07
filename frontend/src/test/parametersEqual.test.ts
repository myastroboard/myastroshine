import { describe, expect, it } from 'vitest';

import { DEFAULT_GEOMETRY, DEFAULT_PARAMETERS, parametersEqual } from '@/types';

describe('parametersEqual', () => {
  it('is true for two untouched default parameter sets', () => {
    expect(parametersEqual(DEFAULT_PARAMETERS, { ...DEFAULT_PARAMETERS })).toBe(true);
  });

  it('is false when a scalar parameter differs', () => {
    expect(parametersEqual(DEFAULT_PARAMETERS, { ...DEFAULT_PARAMETERS, contrast: 1.5 })).toBe(false);
  });

  it('is false when the framing differs', () => {
    expect(
      parametersEqual(DEFAULT_PARAMETERS, {
        ...DEFAULT_PARAMETERS,
        geometry: { ...DEFAULT_GEOMETRY, rotateQuarters: 2 },
      }),
    ).toBe(false);
  });

  it('is true when tone curves match point for point (by value, not reference)', () => {
    const points = [
      { x: 0, y: 0 },
      { x: 128, y: 150 },
      { x: 255, y: 255 },
    ];
    expect(
      parametersEqual(
        { ...DEFAULT_PARAMETERS, curvePoints: points },
        { ...DEFAULT_PARAMETERS, curvePoints: points.map((p) => ({ ...p })) },
      ),
    ).toBe(true);
  });

  it('is false when a tone curve differs by a single output level', () => {
    expect(
      parametersEqual(
        {
          ...DEFAULT_PARAMETERS,
          redCurvePoints: [
            { x: 0, y: 0 },
            { x: 255, y: 255 },
          ],
        },
        {
          ...DEFAULT_PARAMETERS,
          redCurvePoints: [
            { x: 0, y: 0 },
            { x: 255, y: 250 },
          ],
        },
      ),
    ).toBe(false);
  });

  it('is false when a tone curve gained a point', () => {
    expect(
      parametersEqual(DEFAULT_PARAMETERS, {
        ...DEFAULT_PARAMETERS,
        curvePoints: [
          { x: 0, y: 0 },
          { x: 255, y: 255 },
        ],
      }),
    ).toBe(false);
  });
});
