import { useRef, useState, type ChangeEvent } from 'react';

import { FormError } from '@/components/AdminAuthForms';
import { useTranslation } from '@/hooks/useTranslation';
import { apiClient } from '@/services/api';
import { errorMessage } from '@/services/apiError';
import type { EngineStatus, ExternalEngine, StagedEngine } from '@/types';

const ACCEPT = '.zip,.tar.gz,.tgz,.tar.xz,.txz,.tar';

export interface EngineInstallerProps {
  engine: ExternalEngine;
  /** Display name: StarNet2 / DeepSNR. */
  name: string;
  status?: EngineStatus;
  /** The engine was installed or removed: its path setting is now ``path``. */
  onChanged: (path: string) => void;
}

/**
 * Install an engine from the archive the operator downloaded from starnetastro.com:
 * upload it, read the licence shipped in the package, accept it, install. Or
 * remove the package installed that way. Nothing here is bundled with the app.
 */
export function EngineInstaller({ engine, name, status, onChanged }: EngineInstallerProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [staged, setStaged] = useState<StagedEngine | null>(null);
  const [accepted, setAccepted] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fail = (err: unknown) => setError(errorMessage(err, t, t('settings.engines.errors.generic')));

  async function handlePick(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) {
      return;
    }
    setError(null);
    setBusy(true);
    setProgress(0);
    try {
      setStaged(await apiClient.stageEngine(engine, file, setProgress));
      setAccepted(false);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
      setProgress(null);
    }
  }

  async function handleInstall(pending: StagedEngine) {
    setBusy(true);
    setError(null);
    try {
      const installed = await apiClient.installEngine(engine, pending.stagingId);
      setStaged(null);
      onChanged(installed.installed?.path ?? '');
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function handleCancel(pending: StagedEngine) {
    setStaged(null);
    try {
      await apiClient.discardStagedEngine(engine, pending.stagingId);
    } catch {
      // Best effort: an abandoned staging directory is pruned by the hourly cleanup.
    }
  }

  async function handleRemove() {
    if (!confirmRemove) {
      setConfirmRemove(true);
      return;
    }
    setConfirmRemove(false);
    setBusy(true);
    setError(null);
    try {
      await apiClient.removeEngine(engine);
      onChanged('');
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  const installed = status?.installed ?? null;

  return (
    <div className="flex flex-col gap-2 py-2">
      {installed && (
        <div className="flex flex-wrap items-center gap-3">
          <p className="mr-auto text-xs text-muted">
            {t('settings.engines.installed', {
              archive: installed.archiveName,
              version: installed.version ?? '?',
              date: new Date(installed.licenseAcceptedAt).toLocaleDateString(),
            })}
          </p>
          <button
            type="button"
            className="btn btn-danger btn-sm"
            disabled={busy}
            onClick={() => void handleRemove()}
            onBlur={() => setConfirmRemove(false)}
          >
            {confirmRemove ? t('settings.engines.confirm_remove') : t('settings.engines.remove')}
          </button>
        </div>
      )}

      {!staged && (
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="btn btn-outline btn-sm"
            disabled={busy}
            onClick={() => inputRef.current?.click()}
          >
            {installed
              ? t('settings.engines.replace', { name })
              : t('settings.engines.install_from_archive', { name })}
          </button>
          {busy && progress !== null && (
            <span className="text-xs text-muted">
              {progress < 1
                ? t('settings.engines.uploading', { percent: Math.round(progress * 100) })
                : t('settings.engines.checking')}
            </span>
          )}
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            className="hidden"
            aria-label={t('settings.engines.archive_input', { name })}
            onChange={(event) => void handlePick(event)}
          />
        </div>
      )}

      {staged && (
        <div className="panel-inset flex flex-col gap-3">
          <div>
            <p className="text-sm font-medium text-ink">
              {t('settings.engines.license_heading', { name })}
            </p>
            <p className="mt-0.5 text-xs text-muted">
              {t('settings.engines.license_intro', {
                archive: staged.archiveName,
                detail: staged.status.detail,
              })}
            </p>
          </div>
          <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-md border border-line bg-canvas p-3 font-mono text-[11px] text-muted">
            {staged.licenseText}
          </pre>
          <label className="flex items-start gap-2 text-xs text-ink">
            <input
              type="checkbox"
              className="mt-0.5 size-4 shrink-0 accent-accent"
              checked={accepted}
              onChange={(event) => setAccepted(event.target.checked)}
            />
            {t('settings.engines.accept', { name })}
          </label>
          <div className="flex gap-2">
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={!accepted || busy}
              onClick={() => void handleInstall(staged)}
            >
              {t('settings.engines.install')}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={busy}
              onClick={() => void handleCancel(staged)}
            >
              {t('common.cancel')}
            </button>
          </div>
        </div>
      )}

      {error && <FormError>{error}</FormError>}
    </div>
  );
}
