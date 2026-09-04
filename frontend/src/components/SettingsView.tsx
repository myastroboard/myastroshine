import { useState, type ReactNode } from 'react';

import { TokenManager } from '@/components/TokenManager';
import { useAppSettings } from '@/hooks/useAppSettings';
import { useLogs } from '@/hooks/useLogs';
import type { AppSettings, LogLevel } from '@/types';

type Section = 'general' | 'webhooks' | 'advanced' | 'logs';

const SECTIONS: { id: Section; label: string; blurb: string }[] = [
  { id: 'general', label: 'General', blurb: 'Uploads, processing, and stacking defaults.' },
  { id: 'webhooks', label: 'Webhooks', blurb: 'AstroDex tokens and callback delivery.' },
  { id: 'advanced', label: 'Advanced', blurb: 'Networking and log levels.' },
  { id: 'logs', label: 'Logs', blurb: 'Tail, clear, and export the application log.' },
];

const LOG_LEVELS: LogLevel[] = ['debug', 'info', 'warning', 'error', 'critical'];

interface SectionProps {
  draft: AppSettings;
  patch: (changes: Partial<AppSettings>) => void;
}

/**
 * Standalone runtime-configuration page (route `#/settings`). Reads and writes
 * `app_settings.json` through `/api/admin/app-settings`; nothing here is an
 * environment variable.
 */
export function SettingsView({ onClose }: { onClose: () => void }) {
  const { draft, patch, reset, save, dirty, isLoading, isSaving, error } = useAppSettings();
  const [section, setSection] = useState<Section>('general');
  const current = SECTIONS.find((entry) => entry.id === section) ?? SECTIONS[0];

  return (
    <main className="mx-auto w-full max-w-4xl px-4 pb-24 pt-8 sm:px-6">
      <div className="flex flex-col gap-1">
        <button
          type="button"
          className="mb-2 -ml-1 flex w-fit items-center gap-1 rounded px-1 text-xs text-muted outline-none transition-colors hover:text-ink focus-visible:ring-2 focus-visible:ring-accent"
          onClick={onClose}
        >
          <span aria-hidden>&lsaquo;</span> Back to editor
        </button>
        <h1 className="text-xl font-semibold tracking-tight text-ink">Settings</h1>
        <p className="text-sm text-muted">
          Runtime configuration. Stored in the data volume, applied without a redeploy.
        </p>
      </div>

      {error && (
        <p className="mt-4 rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="mt-8 grid gap-x-10 gap-y-6 lg:grid-cols-[188px_minmax(0,1fr)]">
        <nav
          className="flex gap-1 overflow-x-auto lg:sticky lg:top-20 lg:h-fit lg:flex-col lg:overflow-visible"
          aria-label="Settings sections"
        >
          {SECTIONS.map((entry) => (
            <button
              key={entry.id}
              type="button"
              aria-current={section === entry.id ? 'page' : undefined}
              onClick={() => setSection(entry.id)}
              className={
                'shrink-0 rounded-md px-3 py-2 text-left text-sm transition-colors outline-none focus-visible:ring-2 focus-visible:ring-accent ' +
                (section === entry.id
                  ? 'bg-raised font-medium text-ink'
                  : 'text-muted hover:bg-white/[0.04] hover:text-ink')
              }
            >
              {entry.label}
            </button>
          ))}
        </nav>

        <div className="min-w-0">
          <div className="mb-5 border-b border-line-strong pb-3">
            <h2 className="text-sm font-semibold text-ink">{current.label}</h2>
            <p className="mt-0.5 text-xs text-muted">{current.blurb}</p>
          </div>

          {isLoading && !draft && <p className="text-xs text-faint">Loading...</p>}

          {section === 'logs' && <LogsSection />}

          {draft && section !== 'logs' && (
            <>
              {section === 'general' && <GeneralSection draft={draft} patch={patch} />}
              {section === 'webhooks' && <WebhooksSection draft={draft} patch={patch} />}
              {section === 'advanced' && <AdvancedSection draft={draft} patch={patch} />}
            </>
          )}
        </div>
      </div>

      {dirty && (
        <div className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-canvas/90 backdrop-blur">
          <div className="mx-auto flex max-w-4xl items-center gap-3 px-4 py-3 sm:px-6">
            <span className="mr-auto text-xs text-muted">Unsaved changes</span>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={reset}
              disabled={isSaving}
            >
              Reset
            </button>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => void save()}
              disabled={isSaving}
            >
              {isSaving ? 'Saving...' : 'Save changes'}
            </button>
          </div>
        </div>
      )}
    </main>
  );
}

// --- sections ----------------------------------------------------------------

function GeneralSection({ draft, patch }: SectionProps) {
  return (
    <div className="flex flex-col">
      <GroupLabel>Uploads and sessions</GroupLabel>
      <NumberRow
        id="max-upload"
        label="Maximum upload size"
        hint="Uploads larger than this are rejected. Megabytes."
        value={draft.maxImageSizeMb}
        min={1}
        max={1024}
        onChange={(maxImageSizeMb) => patch({ maxImageSizeMb })}
      />
      <NumberRow
        id="session-ttl"
        label="Session lifetime"
        hint="How long a session and its working files are kept. Hours."
        value={draft.sessionExpiryHours}
        min={1}
        max={8760}
        onChange={(sessionExpiryHours) => patch({ sessionExpiryHours })}
      />
      <NumberRow
        id="preview-size"
        label="Preview size"
        hint="Longest edge of the fast-display preview image. Pixels."
        value={draft.previewMaxSize}
        min={64}
        max={4096}
        step={64}
        onChange={(previewMaxSize) => patch({ previewMaxSize })}
      />

      <GroupLabel>Processing</GroupLabel>
      <SelectRow
        id="depth-method"
        label="Depth detection"
        hint="Method used to estimate the depth map for the parallax effect."
        value={draft.depthDetectionMethod}
        options={['gradient', 'ml']}
        onChange={(depthDetectionMethod) => patch({ depthDetectionMethod })}
      />
      <ToggleRow
        id="denoise-ml"
        label="ML denoising"
        hint="Higher quality, noticeably slower, and needs the model present."
        checked={draft.denoiseEnableMl}
        onChange={(denoiseEnableMl) => patch({ denoiseEnableMl })}
      />

      <GroupLabel>Stacking defaults</GroupLabel>
      <ToggleRow
        id="stacking-enabled"
        label="Stacking enabled"
        hint="Show the multi-frame stacking mode."
        checked={draft.stackingEnabled}
        onChange={(stackingEnabled) => patch({ stackingEnabled })}
      />
      <NumberRow
        id="stacking-max"
        label="Maximum frames"
        hint="Upper bound on frames accepted for one stack."
        value={draft.stackingMaxFrames}
        min={2}
        max={1000}
        onChange={(stackingMaxFrames) => patch({ stackingMaxFrames })}
      />
      <SelectRow
        id="stacking-aligner"
        label="Aligner"
        hint="Feature detector used to register frames."
        value={draft.stackingDetector}
        options={['orb', 'sift']}
        onChange={(stackingDetector) => patch({ stackingDetector })}
      />
      <SelectRow
        id="stacking-combine"
        label="Combination"
        hint="Default method for combining aligned frames."
        value={draft.stackingCombinationDefault}
        options={['median', 'mean', 'sigma_clip']}
        onChange={(stackingCombinationDefault) => patch({ stackingCombinationDefault })}
      />
      <NumberRow
        id="stacking-sigma"
        label="Cosmic-ray sigma"
        hint="Rejection threshold in robust standard deviations."
        value={draft.stackingCosmicRayThreshold}
        min={0.5}
        max={10}
        step={0.1}
        onChange={(stackingCosmicRayThreshold) => patch({ stackingCosmicRayThreshold })}
      />
    </div>
  );
}

function WebhooksSection({ draft, patch }: SectionProps) {
  return (
    <div className="flex flex-col gap-8">
      <TokenManager />

      <div className="flex flex-col">
        <GroupLabel>Callback delivery</GroupLabel>
        <ListRow
          id="callback-allowlist"
          label="Callback URL allowlist"
          hint="One URL prefix per line. An empty list allows any host (development only)."
          value={draft.astrodexCallbackUrls}
          placeholder="http://myastroboard.local/api/webhooks/enhanced-images"
          onChange={(astrodexCallbackUrls) => patch({ astrodexCallbackUrls })}
        />
        <NumberRow
          id="astrodex-retries"
          label="Maximum retries"
          hint="Delivery attempts before a webhook is marked failed."
          value={draft.astrodexMaxRetries}
          min={1}
          max={10}
          onChange={(astrodexMaxRetries) => patch({ astrodexMaxRetries })}
        />
        <NumberRow
          id="astrodex-delay"
          label="Retry delay"
          hint="Base backoff between attempts. Seconds."
          value={draft.astrodexRetryDelaySeconds}
          min={0}
          max={60}
          step={0.5}
          onChange={(astrodexRetryDelaySeconds) => patch({ astrodexRetryDelaySeconds })}
        />
      </div>
    </div>
  );
}

function AdvancedSection({ draft, patch }: SectionProps) {
  return (
    <div className="flex flex-col">
      <GroupLabel>Network</GroupLabel>
      <ListRow
        id="cors-origins"
        label="CORS origins"
        hint="One origin per line. Takes effect after the api service restarts."
        value={draft.corsOrigins}
        placeholder="http://localhost:3000"
        onChange={(corsOrigins) => patch({ corsOrigins })}
      />

      <GroupLabel>Logging</GroupLabel>
      <SelectRow
        id="log-file-level"
        label="File log level"
        hint="Level written to the rotating log file."
        value={draft.logLevel}
        options={LOG_LEVELS}
        onChange={(logLevel) => patch({ logLevel })}
      />
      <SelectRow
        id="log-console-level"
        label="Console log level"
        hint="Level echoed to the container logs."
        value={draft.consoleLogLevel}
        options={LOG_LEVELS}
        onChange={(consoleLogLevel) => patch({ consoleLogLevel })}
      />
    </div>
  );
}

function LogsSection() {
  const { lines, level, setLevel, levels, refresh, clear, exportZip, isLoading, busy, error } =
    useLogs();
  const [confirmClear, setConfirmClear] = useState(false);

  async function handleClear() {
    if (!confirmClear) {
      setConfirmClear(true);
      return;
    }
    setConfirmClear(false);
    await clear();
  }

  return (
    <div className="flex flex-col gap-4">
      {error && <p className="text-xs text-danger">{error}</p>}

      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-xs text-muted">
          Level
          <select
            className="field w-32 py-1.5"
            value={level}
            onChange={(event) => setLevel(event.target.value as LogLevel | '')}
          >
            <option value="">all</option>
            {LOG_LEVELS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="btn btn-outline btn-sm" onClick={() => void refresh()}>
          Refresh
        </button>
        <button type="button" className="btn btn-outline btn-sm" onClick={() => void exportZip()}>
          Export ZIP
        </button>
        <button
          type="button"
          className="btn btn-danger btn-sm"
          onClick={() => void handleClear()}
          onBlur={() => setConfirmClear(false)}
          disabled={busy}
        >
          {confirmClear ? 'Confirm clear' : 'Clear'}
        </button>
      </div>

      {levels && (
        <p className="text-xs text-faint">
          Levels - file: <span className="text-muted">{levels.file}</span>, console:{' '}
          <span className="text-muted">{levels.console}</span>. Change them on the Advanced tab.
        </p>
      )}

      <pre className="max-h-[440px] overflow-auto rounded-md border border-line bg-canvas p-3 font-mono text-[11px] leading-relaxed whitespace-pre text-muted">
        {isLoading && lines.length === 0
          ? 'Loading...'
          : lines.length === 0
            ? 'No log lines.'
            : lines.join('\n')}
      </pre>
    </div>
  );
}

// --- row primitives --------------------------------------------------------

function GroupLabel({ children }: { children: ReactNode }) {
  return (
    <p className="mt-6 mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-faint first:mt-0">
      {children}
    </p>
  );
}

function SettingsRow({
  id,
  label,
  hint,
  stacked,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  stacked?: boolean;
  children: ReactNode;
}) {
  return (
    <div
      className={
        'grid gap-x-8 gap-y-2 border-b border-hairline py-4 last:border-b-0 ' +
        (stacked
          ? 'grid-cols-1'
          : 'grid-cols-1 sm:grid-cols-[minmax(0,1fr)_15rem] sm:items-center')
      }
    >
      <div className="flex flex-col gap-0.5">
        <label htmlFor={id} className="text-sm font-medium text-ink">
          {label}
        </label>
        {hint && <span className="text-xs text-muted">{hint}</span>}
      </div>
      <div className={stacked ? '' : 'sm:justify-self-end'}>{children}</div>
    </div>
  );
}

function NumberRow({
  id,
  label,
  hint,
  value,
  onChange,
  min,
  max,
  step,
}: {
  id: string;
  label: string;
  hint?: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <SettingsRow id={id} label={label} hint={hint}>
      <input
        id={id}
        type="number"
        className="field w-full tabular-nums sm:w-40"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </SettingsRow>
  );
}

function SelectRow<T extends string>({
  id,
  label,
  hint,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  hint?: string;
  value: T;
  options: readonly T[];
  onChange: (value: T) => void;
}) {
  return (
    <SettingsRow id={id} label={label} hint={hint}>
      <select
        id={id}
        className="field w-full sm:w-40"
        value={value}
        onChange={(event) => onChange(event.target.value as T)}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </SettingsRow>
  );
}

function ToggleRow({
  id,
  label,
  hint,
  checked,
  onChange,
}: {
  id: string;
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <SettingsRow id={id} label={label} hint={hint}>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        className={
          'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border transition-colors outline-none focus-visible:ring-2 focus-visible:ring-accent ' +
          (checked ? 'border-accent bg-accent/80' : 'border-line-strong bg-raised')
        }
      >
        <span
          className={
            'inline-block size-3.5 rounded-full bg-ink transition-transform ' +
            (checked ? 'translate-x-[1.05rem]' : 'translate-x-[0.15rem]')
          }
        />
      </button>
    </SettingsRow>
  );
}

function ListRow({
  id,
  label,
  hint,
  value,
  onChange,
  placeholder,
}: {
  id: string;
  label: string;
  hint?: string;
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
}) {
  return (
    <SettingsRow id={id} label={label} hint={hint} stacked>
      <textarea
        id={id}
        className="field mt-1 min-h-24 w-full font-mono text-xs"
        value={value.join('\n')}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value.split('\n'))}
      />
    </SettingsRow>
  );
}
