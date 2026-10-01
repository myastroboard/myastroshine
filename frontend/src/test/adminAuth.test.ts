import { describe, expect, it } from 'vitest';

import { authErrorMessage, newPasswordProblem } from '@/services/adminAuth';
import { ApiError } from '@/services/api';

const t = (key: string, params?: Record<string, string | number>) =>
  params ? `${key}:${JSON.stringify(params)}` : key;

describe('authErrorMessage', () => {
  it('maps the auth error codes to their messages', () => {
    expect(authErrorMessage(new ApiError(401, 'x', 'INVALID_CREDENTIALS'), t)).toBe(
      'settings.auth.errors.invalid_password',
    );
    expect(authErrorMessage(new ApiError(429, 'x', 'RATE_LIMITED'), t)).toBe(
      'settings.auth.errors.locked_out',
    );
    expect(authErrorMessage(new ApiError(409, 'x', 'ADMIN_ALREADY_CONFIGURED'), t)).toBe(
      'settings.auth.errors.already_configured',
    );
  });

  it('falls back to the raw message, then to the generic one', () => {
    expect(authErrorMessage(new ApiError(400, 'Invalid request parameters'), t)).toBe(
      'Invalid request parameters',
    );
    expect(authErrorMessage('not an error', t)).toBe('settings.auth.errors.generic');
  });
});

describe('newPasswordProblem', () => {
  it('rejects a short password, then a mismatch, and accepts a good pair', () => {
    expect(newPasswordProblem('short', 'short', t)).toBe('settings.auth.errors.too_short:{"min":10}');
    expect(newPasswordProblem('long enough 1', 'long enough 2', t)).toBe(
      'settings.auth.errors.mismatch',
    );
    expect(newPasswordProblem('long enough 1', 'long enough 1', t)).toBeNull();
  });
});

