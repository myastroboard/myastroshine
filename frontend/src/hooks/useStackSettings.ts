import { useState } from 'react';

import type { StackSettings } from '@/types';

export const DEFAULT_STACK_SETTINGS: StackSettings = {
  registrationTransform: 'similarity',
  combinationMethod: 'average',
  rejectionAlgo: 'winsorized_sigma',
  weighting: 'noise',
};

/** Local state for the stacking configuration panel. */
export function useStackSettings(initial: StackSettings = DEFAULT_STACK_SETTINGS) {
  const [settings, setSettings] = useState<StackSettings>(initial);
  return { settings, setSettings };
}
