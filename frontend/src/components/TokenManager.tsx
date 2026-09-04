import { useState, type FormEvent } from 'react';

import { useTokens } from '@/hooks/useTokens';

/** Create, view, and revoke long-lived AstroDex webhook tokens. */
export function TokenManager() {
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
      <h2 className="eyebrow">AstroDex webhook tokens</h2>

      {error && <p className="text-xs text-danger">{error}</p>}

      {justCreated && (
        <div className="flex flex-col gap-1.5 rounded-lg border border-accent/40 bg-accent-wash p-3 text-xs">
          <p className="font-medium text-accent-strong">
            Copy these now, they are not shown again.
          </p>
          <code className="break-all font-mono text-muted">token: {justCreated.token}</code>
          <code className="break-all font-mono text-muted">
            signing_secret: {justCreated.signingSecret}
          </code>
          <button type="button" className="btn btn-ghost btn-sm mt-1 self-start" onClick={dismissCreated}>
            Done
          </button>
        </div>
      )}

      <form className="flex flex-wrap items-end gap-3" onSubmit={handleCreate}>
        <label className="flex flex-col gap-1.5">
          <span className="label">Name</span>
          <input
            className="field w-48"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="AstroDex prod"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="label">Expires (days, optional)</span>
          <input
            type="number"
            min={1}
            className="field w-40"
            value={expiresInDays}
            onChange={(event) => setExpiresInDays(event.target.value)}
          />
        </label>
        <button type="submit" className="btn btn-primary btn-sm" disabled={busy || !name.trim()}>
          Create token
        </button>
      </form>

      <ul className="flex flex-col divide-y divide-hairline text-sm">
        {isLoading && tokens.length === 0 && (
          <li className="py-2 text-xs text-faint">Loading...</li>
        )}
        {tokens.map((token) => (
          <li key={token.id} className="flex items-center justify-between gap-2 py-2.5">
            <span className={token.revoked ? 'text-ghost line-through' : 'text-ink'}>
              {token.name}{' '}
              <span className="font-mono text-xs text-faint">({token.tokenPrefix}...)</span>
              {token.expiresAt && (
                <span className="text-xs text-faint"> expires {token.expiresAt.slice(0, 10)}</span>
              )}
            </span>
            {!token.revoked && (
              <button
                type="button"
                className="btn btn-danger btn-sm"
                onClick={() => void revokeToken(token.id)}
              >
                Revoke
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
