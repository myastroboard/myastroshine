import { useCallback, useEffect, useState } from 'react';

import { apiClient } from '@/services/api';
import type { AppSettings } from '@/types';

/**
 * Loads the runtime settings, holds a local draft the forms edit, and saves the
 * whole object back. `dirty` is true while the draft differs from what is saved.
 */
export function useAppSettings() {
  const [saved, setSaved] = useState<AppSettings | null>(null);
  const [draft, setDraft] = useState<AppSettings | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const settings = await apiClient.getAppSettings();
      setSaved(settings);
      setDraft(settings);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load settings');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const patch = useCallback((changes: Partial<AppSettings>) => {
    setDraft((current) => (current ? { ...current, ...changes } : current));
  }, []);

  const reset = useCallback(() => setDraft(saved), [saved]);

  /** Take in settings the server changed on its own (an engine install sets its
   * path), without discarding the user's other unsaved edits. */
  const applyServerChange = useCallback((changes: Partial<AppSettings>) => {
    setSaved((current) => (current ? { ...current, ...changes } : current));
    setDraft((current) => (current ? { ...current, ...changes } : current));
  }, []);

  const save = useCallback(async () => {
    if (!draft) {
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      const settings = await apiClient.saveAppSettings(draft);
      setSaved(settings);
      setDraft(settings);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save settings');
    } finally {
      setIsSaving(false);
    }
  }, [draft]);

  const dirty = Boolean(draft && saved && JSON.stringify(draft) !== JSON.stringify(saved));

  return {
    draft,
    patch,
    reset,
    save,
    refresh,
    applyServerChange,
    dirty,
    isLoading,
    isSaving,
    error,
  };
}
