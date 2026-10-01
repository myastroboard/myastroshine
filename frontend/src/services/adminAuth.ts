// Helpers for the admin login / password forms (components/AdminAuthForms.tsx,
// components/AdminSecurityPanel.tsx).

import { ApiError } from './api';
import { errorMessage } from './apiError';

/** Mirrors `ADMIN_PASSWORD_MIN_LENGTH` in the backend's app/constants.py. */
export const ADMIN_PASSWORD_MIN_LENGTH = 10;

type Translate = (key: string, params?: Record<string, string | number>) => string;

/** A readable message for a failed admin-auth call. */
export function authErrorMessage(err: unknown, t: Translate): string {
  if (err instanceof ApiError) {
    if (err.code === 'INVALID_CREDENTIALS') {
      return t('settings.auth.errors.invalid_password');
    }
    if (err.status === 429) {
      return t('settings.auth.errors.locked_out');
    }
    if (err.code === 'ADMIN_ALREADY_CONFIGURED') {
      return t('settings.auth.errors.already_configured');
    }
  }
  return errorMessage(err, t, t('settings.auth.errors.generic'));
}

/**
 * Client-side check of a new password + its confirmation. Returns the message to
 * show, or `null` when the pair is acceptable (the backend enforces the same
 * minimum length).
 */
export function newPasswordProblem(password: string, confirm: string, t: Translate): string | null {
  if (password.length < ADMIN_PASSWORD_MIN_LENGTH) {
    return t('settings.auth.errors.too_short', { min: ADMIN_PASSWORD_MIN_LENGTH });
  }
  if (password !== confirm) {
    return t('settings.auth.errors.mismatch');
  }
  return null;
}
