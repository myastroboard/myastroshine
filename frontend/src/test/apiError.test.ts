import { describe, expect, it } from 'vitest';

import { ApiError } from '@/services/api';
import { errorMessage, friendlyErrorKey } from '@/services/apiError';

describe('friendlyErrorKey', () => {
  it('maps a 429 to the "busy" key regardless of the backend message', () => {
    expect(friendlyErrorKey(new ApiError(429, 'Too many concurrent processing jobs'))).toBe(
      'errors.busy',
    );
  });

  it('maps 503 and other 5xx to their own keys', () => {
    expect(friendlyErrorKey(new ApiError(503, 'x'))).toBe('errors.unavailable');
    expect(friendlyErrorKey(new ApiError(500, 'x'))).toBe('errors.server');
  });

  it('returns null for a 4xx that is not rate limiting, and for a plain Error', () => {
    expect(friendlyErrorKey(new ApiError(404, 'not found'))).toBeNull();
    expect(friendlyErrorKey(new Error('boom'))).toBeNull();
  });
});

describe('errorMessage', () => {
  const t = (key: string) => (key === 'errors.busy' ? 'Le serveur est occupe' : key);

  it('translates a known error class', () => {
    expect(errorMessage(new ApiError(429, 'raw english'), t, 'fallback')).toBe(
      'Le serveur est occupe',
    );
  });

  it('falls back to the raw message for an unmapped error', () => {
    expect(errorMessage(new ApiError(404, 'Session not found'), t, 'fallback')).toBe(
      'Session not found',
    );
  });

  it('uses the fallback when the value is not an Error', () => {
    expect(errorMessage('a string', t, 'fallback')).toBe('fallback');
  });
});
