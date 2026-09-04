import { describe, expect, it } from 'vitest';

import { keysToCamelCase, keysToSnakeCase } from '@/services/caseConvert';

describe('caseConvert', () => {
  it('converts nested object keys to snake_case', () => {
    const input = {
      sessionId: 'abc',
      parameters: { depthShiftIntensity: 10, contrast: 1.5 },
      depthLayers: [{ layerId: 0, imageUrl: '/x' }],
    };

    expect(keysToSnakeCase(input)).toEqual({
      session_id: 'abc',
      parameters: { depth_shift_intensity: 10, contrast: 1.5 },
      depth_layers: [{ layer_id: 0, image_url: '/x' }],
    });
  });

  it('converts nested object keys to camelCase', () => {
    const input = {
      preset_id: 'system_nebula',
      is_favorite: false,
      parameters: { depth_shift_intensity: 0 },
    };

    expect(keysToCamelCase(input)).toEqual({
      presetId: 'system_nebula',
      isFavorite: false,
      parameters: { depthShiftIntensity: 0 },
    });
  });

  it('round-trips camel -> snake -> camel', () => {
    const original = { estimatedSnrImprovement: 3.87, stackedImageUrl: '/s', frameCount: 15 };
    expect(keysToCamelCase(keysToSnakeCase(original))).toEqual(original);
  });

  it('leaves primitives and arrays of primitives untouched', () => {
    expect(keysToCamelCase({ r: [1, 2, 3], total: 5, name: 'Nebula' })).toEqual({
      r: [1, 2, 3],
      total: 5,
      name: 'Nebula',
    });
  });
});
