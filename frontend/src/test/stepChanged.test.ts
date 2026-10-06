import { describe, expect, it } from 'vitest';

import {
  DEFAULT_LOOK_PARAMETERS,
  DEFAULT_PARAMETERS,
  DEFAULT_STACK_PARAMETERS,
  EDITOR_STEPS,
  stepChanged,
  stepIsModified,
  type EditorStepId,
  type ProcessingParameters,
} from '@/types';

const step = (id: EditorStepId) => EDITOR_STEPS.find((entry) => entry.id === id)!;
const base: ProcessingParameters = DEFAULT_PARAMETERS;

describe('stepChanged', () => {
  it('never flags the start and export brackets', () => {
    const edited = { ...base, exposure: 1 };
    expect(stepChanged(step('start'), base, edited, null, null)).toBe(false);
    expect(stepChanged(step('export'), base, edited, null, null)).toBe(false);
  });

  it('flags a slider step only when one of its own parameters differs', () => {
    expect(stepChanged(step('light'), base, { ...base, exposure: 0.2 }, null, null)).toBe(true);
    expect(stepChanged(step('light'), base, { ...base, saturation: 1.5 }, null, null)).toBe(false);
  });

  it('compares the linear stack stage and the framing', () => {
    const stack = { ...base, stack: { ...DEFAULT_STACK_PARAMETERS, stretch: 0.9 } };
    expect(stepChanged(step('stack'), base, stack, null, null)).toBe(true);
    const framed = { ...base, geometry: { ...base.geometry, rotateQuarters: 1 } };
    expect(stepChanged(step('frame'), base, framed, null, null)).toBe(true);
    expect(stepChanged(step('frame'), framed, framed, null, null)).toBe(false);
  });

  it('compares every tone curve point by point', () => {
    const curve = [
      { x: 0, y: 0 },
      { x: 0.5, y: 0.6 },
      { x: 1, y: 1 },
    ];
    const withMaster = { ...base, curvePoints: curve };
    expect(stepChanged(step('curves'), base, withMaster, null, null)).toBe(true);
    expect(stepChanged(step('curves'), withMaster, { ...withMaster }, null, null)).toBe(false);

    const moved = { ...withMaster, curvePoints: [curve[0], { x: 0.5, y: 0.7 }, curve[2]] };
    expect(stepChanged(step('curves'), withMaster, moved, null, null)).toBe(true);
    for (const channel of ['redCurvePoints', 'greenCurvePoints', 'blueCurvePoints'] as const) {
      expect(stepChanged(step('curves'), base, { ...base, [channel]: curve }, null, null)).toBe(true);
    }
  });

  it('compares the Depth Shift focal point, set or not', () => {
    const depth = step('depth');
    expect(stepChanged(depth, base, base, null, null)).toBe(false);
    expect(stepChanged(depth, base, base, null, { x: 0.5, y: 0.5 })).toBe(true);
    expect(stepChanged(depth, base, base, { x: 0.5, y: 0.5 }, null)).toBe(true);
    expect(stepChanged(depth, base, base, { x: 0.5, y: 0.5 }, { x: 0.5, y: 0.5 })).toBe(false);
    expect(stepChanged(depth, base, base, { x: 0.5, y: 0.5 }, { x: 0.5, y: 0.2 })).toBe(true);
    expect(stepChanged(depth, base, base, { x: 0.5, y: 0.5 }, { x: 0.1, y: 0.5 })).toBe(true);
  });
});

describe('stepIsModified', () => {
  it('measures a step against the defaults', () => {
    expect(stepIsModified(step('colour'), base, null)).toBe(false);
    expect(stepIsModified(step('colour'), { ...base, vibrance: 1.4 }, null)).toBe(true);
    expect(stepIsModified(step('depth'), base, { x: 0.3, y: 0.3 })).toBe(true);
  });

  it('flags the style step for a chosen look and its amount, not for an unused amount', () => {
    const vivid = { ...base, look: { lookId: 'vivid' as const, amount: 60 } };
    expect(stepChanged(step('style'), base, vivid, null, null)).toBe(true);
    const stronger = { ...base, look: { lookId: 'vivid' as const, amount: 90 } };
    expect(stepChanged(step('style'), vivid, stronger, null, null)).toBe(true);
    const unusedAmount = { ...base, look: { ...DEFAULT_LOOK_PARAMETERS, amount: 10 } };
    expect(stepChanged(step('style'), base, unusedAmount, null, null)).toBe(false);
    expect(stepIsModified(step('style'), vivid, null)).toBe(true);
  });
});
