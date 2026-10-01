import { useCallback, useEffect, useState, type FormEvent } from 'react';

import { FormError, PasswordField } from '@/components/AdminAuthForms';
import { useTranslation } from '@/hooks/useTranslation';
import { authErrorMessage, newPasswordProblem } from '@/services/adminAuth';
import { apiClient } from '@/services/api';
import type { AdminSession } from '@/types';

/**
 * Settings -> Security: change the admin password, and see / log out the
 * browsers currently logged in as admin. `onSignedOut` runs when the admin logs
 * out this very browser from the list.
 */
export function AdminSecurityPanel({ onSignedOut }: { onSignedOut: () => void }) {
  return (
    <div className="flex flex-col gap-6">
      <ChangePasswordForm />
      <SessionList onSignedOut={onSignedOut} />
    </div>
  );
}

function ChangePasswordForm() {
  const { t } = useTranslation();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setDone(false);
    const problem = newPasswordProblem(next, confirm, t);
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await apiClient.changeAdminPassword(current, next);
      setCurrent('');
      setNext('');
      setConfirm('');
      setDone(true);
    } catch (err) {
      setError(authErrorMessage(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel-inset flex flex-col gap-3" onSubmit={(event) => void handleSubmit(event)}>
      <div>
        <h3 className="text-sm font-semibold text-ink">{t('settings.security.change_password.title')}</h3>
        <p className="mt-0.5 text-xs text-muted">{t('settings.security.change_password.blurb')}</p>
      </div>
      <PasswordField
        id="admin-current-password"
        label={t('settings.auth.current_password')}
        value={current}
        onChange={setCurrent}
        autoComplete="current-password"
      />
      <PasswordField
        id="admin-new-password"
        label={t('settings.auth.new_password')}
        value={next}
        onChange={setNext}
        autoComplete="new-password"
      />
      <PasswordField
        id="admin-confirm-password"
        label={t('settings.auth.confirm_password')}
        value={confirm}
        onChange={setConfirm}
        autoComplete="new-password"
      />
      {error && <FormError>{error}</FormError>}
      {done && (
        <p role="status" className="text-xs text-success">
          {t('settings.security.change_password.done')}
        </p>
      )}
      <button
        type="submit"
        className="btn btn-primary btn-sm w-fit"
        disabled={busy || !current || !next}
      >
        {busy ? t('common.saving') : t('settings.security.change_password.submit')}
      </button>
    </form>
  );
}

function SessionList({ onSignedOut }: { onSignedOut: () => void }) {
  const { t } = useTranslation();
  const [sessions, setSessions] = useState<AdminSession[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setSessions(await apiClient.listAdminSessions());
      setError(null);
    } catch (err) {
      setError(authErrorMessage(err, t));
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  async function revoke(session: AdminSession) {
    try {
      await apiClient.revokeAdminSession(session.id);
    } catch (err) {
      setError(authErrorMessage(err, t));
      return;
    }
    if (session.current) {
      onSignedOut();
      return;
    }
    await load();
  }

  return (
    <div className="panel-inset flex flex-col gap-3">
      <div>
        <h3 className="text-sm font-semibold text-ink">{t('settings.security.sessions.title')}</h3>
        <p className="mt-0.5 text-xs text-muted">{t('settings.security.sessions.blurb')}</p>
      </div>
      {error && <FormError>{error}</FormError>}
      {sessions === null && !error && <p className="text-xs text-faint">{t('common.loading')}</p>}
      {sessions && (
        <ul className="flex flex-col divide-y divide-hairline">
          {sessions.map((session) => (
            <li key={session.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2">
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-sm text-ink">
                  {session.userAgent ?? t('settings.security.sessions.unknown_browser')}
                  {session.current && (
                    <span className="ml-2 text-xs font-medium text-accent">
                      {t('settings.security.sessions.this_browser')}
                    </span>
                  )}
                </span>
                <span className="text-xs text-muted">
                  {t('settings.security.sessions.details', {
                    ip: session.clientIp ?? '-',
                    last_seen: new Date(session.lastSeenAt).toLocaleString(),
                  })}
                </span>
              </div>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => void revoke(session)}
              >
                {session.current
                  ? t('settings.auth.logout')
                  : t('settings.security.sessions.revoke')}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
