import { useState } from 'react';

import type { StackSettings } from '@/types';

export const DEFAULT_STACK_SETTINGS: StackSettings = {
  registrationMethod: 'orb',
  combinationMethod: 'median',
  cosmicRayRejection: true,
  backgroundNormalization: true,
};

/** Local state for the stacking configuration panel (v1.1+). */
export function useStackSettings(initial: StackSettings = DEFAULT_STACK_SETTINGS) {
  const [settings, setSettings] = useState<StackSettings>(initial);
  return { settings, setSettings };
}
