import { useState, type FormEvent, type ReactNode } from 'react';

import { useTranslation } from '@/hooks/useTranslation';
import {
  ADMIN_PASSWORD_MIN_LENGTH,
  authErrorMessage,
  newPasswordProblem,
} from '@/services/adminAuth';

export function PasswordField({
  id,
  label,
  value,
  onChange,
  autoComplete,
  autoFocus,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: 'current-password' | 'new-password';
  autoFocus?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
      </label>
      <input
        id={id}
        type="password"
        className="field w-full"
        value={value}
        autoComplete={autoComplete}
        autoFocus={autoFocus}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

export function FormError({ children }: { children: ReactNode }) {
  return (
    <p
      role="alert"
      className="rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-xs text-danger"
    >
      {children}
    </p>
  );
}

function GateCard({
  title,
  blurb,
  onSubmit,
  children,
}: {
  title: string;
  blurb: string;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  children: ReactNode;
}) {
  return (
    <form className="panel mx-auto mt-8 flex w-full max-w-md flex-col gap-4" onSubmit={onSubmit}>
      <div>
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
        <p className="mt-1 text-xs text-muted">{blurb}</p>
      </div>
      {children}
    </form>
  );
}

/** First run: choose the admin password (typed twice). */
export function AdminSetupForm({ onSubmit }: { onSubmit: (password: string) => Promise<void> }) {
  const { t } = useTranslation();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const problem = newPasswordProblem(password, confirm, t);
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSubmit(password);
    } catch (err) {
      setError(authErrorMessage(err, t));
      setBusy(false);
    }
  }

  return (
    <GateCard
      title={t('settings.auth.setup.title')}
      blurb={t('settings.auth.setup.blurb', { min: ADMIN_PASSWORD_MIN_LENGTH })}
      onSubmit={(event) => void handleSubmit(event)}
    >
      <PasswordField
        id="admin-setup-password"
        label={t('settings.auth.new_password')}
        value={password}
        onChange={setPassword}
        autoComplete="new-password"
        autoFocus
      />
      <PasswordField
        id="admin-setup-confirm"
        label={t('settings.auth.confirm_password')}
        value={confirm}
        onChange={setConfirm}
        autoComplete="new-password"
      />
      {error && <FormError>{error}</FormError>}
      <button type="submit" className="btn btn-primary btn-sm w-fit" disabled={busy}>
        {busy ? t('common.saving') : t('settings.auth.setup.submit')}
      </button>
    </GateCard>
  );
}

/** The admin password is set: log in to reach the settings. */
export function AdminLoginForm({ onSubmit }: { onSubmit: (password: string) => Promise<void> }) {
  const { t } = useTranslation();
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!password) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSubmit(password);
    } catch (err) {
      setError(authErrorMessage(err, t));
      setPassword('');
      setBusy(false);
    }
  }

  return (
    <GateCard
      title={t('settings.auth.login.title')}
      blurb={t('settings.auth.login.blurb')}
      onSubmit={(event) => void handleSubmit(event)}
    >
      <PasswordField
        id="admin-login-password"
        label={t('settings.auth.password')}
        value={password}
        onChange={setPassword}
        autoComplete="current-password"
        autoFocus
      />
      {error && <FormError>{error}</FormError>}
      <button type="submit" className="btn btn-primary btn-sm w-fit" disabled={busy}>
        {busy ? t('common.loading') : t('settings.auth.login.submit')}
      </button>
    </GateCard>
  );
}
