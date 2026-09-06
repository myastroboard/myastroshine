import { ApiError } from './api';

/**
 * An i18n key for errors worth showing in the user's own language rather than
 * the raw backend string, or `null` to fall back to `err.message`.
 *
 * Backend error *detail* text is English-only by project convention, but a few
 * whole classes of failure are common, recoverable, and not worth surfacing in
 * English (the server is busy, or briefly unavailable).
 */
export function friendlyErrorKey(err: unknown): string | null {
  if (err instanceof ApiError) {
    if (err.status === 429) {
      return 'errors.busy';
    }
    if (err.status === 503) {
      return 'errors.unavailable';
    }
    if (err.status >= 500) {
      return 'errors.server';
    }
  }
  return null;
}

/** Resolve an error to a message: a translated one for known classes, else the
 * raw message, else `fallback`. `t` is `useTranslation()`'s `t`. */
export function errorMessage(
  err: unknown,
  t: (key: string) => string,
  fallback: string,
): string {
  const key = friendlyErrorKey(err);
  if (key) {
    return t(key);
  }
  return err instanceof Error ? err.message : fallback;
}
