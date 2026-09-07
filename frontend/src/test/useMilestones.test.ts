import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useMilestones } from '@/hooks/useMilestones';
import { DEFAULT_PARAMETERS, type ProcessingParameters } from '@/types';

describe('useMilestones', () => {
  it('starts with a single origin milestone, active at the defaults', () => {
    const { result } = renderHook(() => useMilestones('s1', DEFAULT_PARAMETERS, null));

    expect(result.current.milestones).toHaveLength(1);
    expect(result.current.milestones[0]).toMatchObject({ kind: 'origin', ordinal: 0 });
    expect(result.current.activeId).toBe(result.current.milestones[0].id);
  });

  it('captures the current edit state as a new saved milestone', () => {
    const edited: ProcessingParameters = { ...DEFAULT_PARAMETERS, exposure: 0.5 };
    const { result } = renderHook(({ p }) => useMilestones('s1', p, null), {
      initialProps: { p: edited },
    });

    act(() => result.current.capture());

    expect(result.current.milestones).toHaveLength(2);
    expect(result.current.milestones[1]).toMatchObject({ kind: 'saved', ordinal: 1 });
    expect(result.current.activeId).toBe(result.current.milestones[1].id);
  });

  it('numbers each saved milestone in order', () => {
    const { result, rerender } = renderHook(({ p }) => useMilestones('s1', p, null), {
      initialProps: { p: { ...DEFAULT_PARAMETERS, exposure: 0.1 } as ProcessingParameters },
    });

    act(() => result.current.capture());
    rerender({ p: { ...DEFAULT_PARAMETERS, exposure: 0.2 } });
    act(() => result.current.capture());

    expect(result.current.milestones.map((m) => m.ordinal)).toEqual([0, 1, 2]);
  });

  it('clears activeId once the parameters diverge from every milestone', () => {
    const { result, rerender } = renderHook(({ p }) => useMilestones('s1', p, null), {
      initialProps: { p: DEFAULT_PARAMETERS as ProcessingParameters },
    });

    act(() => result.current.capture()); // milestone 1 == current defaults
    rerender({ p: { ...DEFAULT_PARAMETERS, contrast: 2 } });

    expect(result.current.activeId).toBeNull();
  });

  it('re-matches a milestone when the parameters land back on its snapshot', () => {
    const { result, rerender } = renderHook(({ p }) => useMilestones('s1', p, null), {
      initialProps: { p: DEFAULT_PARAMETERS as ProcessingParameters },
    });

    act(() => result.current.capture());
    rerender({ p: { ...DEFAULT_PARAMETERS, contrast: 2 } });
    rerender({ p: DEFAULT_PARAMETERS });

    expect(result.current.activeId).toBe(result.current.milestones[0].id);
  });

  it('resets to just the origin when the session changes', () => {
    const { result, rerender } = renderHook(
      ({ s }) => useMilestones(s, DEFAULT_PARAMETERS, null),
      { initialProps: { s: 's1' } },
    );

    act(() => result.current.capture());
    expect(result.current.milestones).toHaveLength(2);

    rerender({ s: 's2' });

    expect(result.current.milestones).toHaveLength(1);
    expect(result.current.milestones[0].kind).toBe('origin');
  });
});
