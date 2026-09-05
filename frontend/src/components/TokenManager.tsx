import { useState, type FormEvent } from 'react';

import { useTokens } from '@/hooks/useTokens';
import { useTranslation } from '@/hooks/useTranslation';

/** Create, view, and revoke long-lived AstroDex webhook tokens. */
export function TokenManager() {
  const { t } = useTranslation();
  const { tokens, justCreated, dismissCreated, createToken, revokeToken, isLoading, error } =
    useTokens();
  const [name, setName] = useState('');
  const [expiresInDays, setExpiresInDays] = useState('');
  const [busy, setBusy] = useState(false);

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) {
      return;
    }
    setBusy(true);
    try {
      await createToken(name.trim(), expiresInDays ? Number(expiresInDays) : undefined);
      setName('');
      setExpiresInDays('');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel flex flex-col gap-4">
      <h2 className="eyebrow">{t('token_manager.heading')}</h2>

      {error && <p className="text-xs text-danger">{error}</p>}

      {justCreated && (
        <div className="flex flex-col gap-1.5 rounded-lg border border-accent/40 bg-accent-wash p-3 text-xs">
          <p className="font-medium text-accent-strong">{t('token_manager.copy_now_warning')}</p>
          <code className="break-all font-mono text-muted">token: {justCreated.token}</code>
          <code className="break-all font-mono text-muted">
            signing_secret: {justCreated.signingSecret}
          </code>
          <button type="button" className="btn btn-ghost btn-sm mt-1 self-start" onClick={dismissCreated}>
            {t('token_manager.done')}
          </button>
        </div>
      )}

      <form className="flex flex-wrap items-end gap-3" onSubmit={handleCreate}>
        <label className="flex flex-col gap-1.5">
          <span className="label">{t('common.name')}</span>
          <input
            className="field w-48"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={t('token_manager.name_placeholder')}
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="label">{t('token_manager.expires_label')}</span>
          <input
            type="number"
            min={1}
            className="field w-40"
            value={expiresInDays}
            onChange={(event) => setExpiresInDays(event.target.value)}
          />
        </label>
        <button type="submit" className="btn btn-primary btn-sm" disabled={busy || !name.trim()}>
          {t('token_manager.create_button')}
        </button>
      </form>

      <ul className="flex flex-col divide-y divide-hairline text-sm">
        {isLoading && tokens.length === 0 && (
          <li className="py-2 text-xs text-faint">{t('common.loading')}</li>
        )}
        {tokens.map((token) => (
          <li key={token.id} className="flex items-center justify-between gap-2 py-2.5">
            <span className={token.revoked ? 'text-ghost line-through' : 'text-ink'}>
              {token.name}{' '}
              <span className="font-mono text-xs text-faint">({token.tokenPrefix}...)</span>
              {token.expiresAt && (
                <span className="text-xs text-faint">
                  {' '}
                  {t('token_manager.expires_on', { date: token.expiresAt.slice(0, 10) })}
                </span>
              )}
            </span>
            {!token.revoked && (
              <button
                type="button"
                className="btn btn-danger btn-sm"
                onClick={() => void revokeToken(token.id)}
              >
                {t('token_manager.revoke_button')}
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
