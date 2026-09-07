import { useCallback, useEffect, useRef, useState } from 'react';

import {
  DEFAULT_PARAMETERS,
  parametersEqual,
  type FocusPoint,
  type ProcessingParameters,
} from '@/types';

export interface Milestone {
  id: string;
  kind: 'origin' | 'saved';
  /** 0 for the original image, then 1, 2, ... for each saved milestone. */
  ordinal: number;
  parameters: ProcessingParameters;
  focalPoint: FocusPoint | null;
  createdAt: number;
}

function focusPointsEqual(a: FocusPoint | null, b: FocusPoint | null): boolean {
  if (a === null || b === null) {
    return a === b;
  }
  return a.x === b.x && a.y === b.y;
}

function originMilestone(sessionId: string): Milestone {
  return {
    id: `${sessionId}-0`,
    kind: 'origin',
    ordinal: 0,
    parameters: DEFAULT_PARAMETERS,
    focalPoint: null,
    createdAt: Date.now(),
  };
}

/**
 * In-memory edit milestones for the current image session. The first entry is
 * always the original image; `capture()` appends a snapshot of the current edit
 * state (all parameters, the framing, and the Depth Shift focal point). Nothing
 * is persisted - a new image (new `sessionId`) starts over, and milestones
 * cannot be deleted.
 *
 * `activeId` is the milestone whose snapshot matches the current edit state, or
 * `null` once the adjustments have diverged from every one - derived, so it
 * re-highlights on its own if the sliders land back on a milestone's values.
 */
export function useMilestones(
  sessionId: string,
  parameters: ProcessingParameters,
  focalPoint: FocusPoint | null,
) {
  const [milestones, setMilestones] = useState<Milestone[]>(() => [originMilestone(sessionId)]);
  const nextOrdinal = useRef(1);
  const sessionRef = useRef(sessionId);

  // capture() reads the live edit state from here so its identity stays stable.
  const snapshot = useRef({ parameters, focalPoint });
  snapshot.current = { parameters, focalPoint };

  // A new image wipes the milestones (EditorView also remounts on a new session
  // today, but keep the hook correct on its own).
  useEffect(() => {
    if (sessionRef.current === sessionId) {
      return;
    }
    sessionRef.current = sessionId;
    nextOrdinal.current = 1;
    setMilestones([originMilestone(sessionId)]);
  }, [sessionId]);

  const capture = useCallback(() => {
    const ordinal = nextOrdinal.current;
    nextOrdinal.current += 1;
    setMilestones((prev) => [
      ...prev,
      {
        id: `${sessionRef.current}-${ordinal}`,
        kind: 'saved',
        ordinal,
        parameters: snapshot.current.parameters,
        focalPoint: snapshot.current.focalPoint,
        createdAt: Date.now(),
      },
    ]);
  }, []);

  const activeId =
    milestones.find(
      (milestone) =>
        parametersEqual(milestone.parameters, parameters) &&
        focusPointsEqual(milestone.focalPoint, focalPoint),
    )?.id ?? null;

  return { milestones, activeId, capture };
}
