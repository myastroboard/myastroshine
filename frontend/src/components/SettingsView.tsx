import { useState, type ReactNode } from 'react';

import { TokenManager } from '@/components/TokenManager';
import { useAppSettings } from '@/hooks/useAppSettings';
import { useLogs } from '@/hooks/useLogs';
import { useTranslation } from '@/hooks/useTranslation';
import type { AppSettings, LogLevel } from '@/types';

type Section = 'general' | 'webhooks' | 'advanced' | 'logs';

const SECTIONS: Section[] = ['general', 'webhooks', 'advanced', 'logs'];

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
  const { t } = useTranslation();
  const { draft, patch, reset, save, dirty, isLoading, isSaving, error } = useAppSettings();
  const [section, setSection] = useState<Section>('general');

  return (
    <main className="mx-auto w-full max-w-4xl px-4 pb-24 pt-8 sm:px-6">
      <div className="flex flex-col gap-1">
        <button
          type="button"
          className="mb-2 -ml-1 flex w-fit items-center gap-1 rounded px-1 text-xs text-muted outline-none transition-colors hover:text-ink focus-visible:ring-2 focus-visible:ring-accent"
          onClick={onClose}
        >
          <span aria-hidden>&lsaquo;</span> {t('settings.back_to_editor')}
        </button>
        <h1 className="text-xl font-semibold tracking-tight text-ink">{t('settings.heading')}</h1>
        <p className="text-sm text-muted">{t('settings.subheading')}</p>
      </div>

      {error && (
        <p className="mt-4 rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="mt-8 grid gap-x-10 gap-y-6 lg:grid-cols-[188px_minmax(0,1fr)]">
        <nav
          className="flex gap-1 overflow-x-auto lg:sticky lg:top-20 lg:h-fit lg:flex-col lg:overflow-visible"
          aria-label={t('settings.sections_aria_label')}
        >
          {SECTIONS.map((entry) => (
            <button
              key={entry}
              type="button"
              aria-current={section === entry ? 'page' : undefined}
              onClick={() => setSection(entry)}
              className={
                'shrink-0 rounded-md px-3 py-2 text-left text-sm transition-colors outline-none focus-visible:ring-2 focus-visible:ring-accent ' +
                (section === entry
                  ? 'bg-raised font-medium text-ink'
                  : 'text-muted hover:bg-white/[0.04] hover:text-ink')
              }
            >
              {t(`settings.sections.${entry}.label`)}
            </button>
          ))}
        </nav>

        <div className="min-w-0">
          <div className="mb-5 border-b border-line-strong pb-3">
            <h2 className="text-sm font-semibold text-ink">{t(`settings.sections.${section}.label`)}</h2>
            <p className="mt-0.5 text-xs text-muted">{t(`settings.sections.${section}.blurb`)}</p>
          </div>

          {isLoading && !draft && <p className="text-xs text-faint">{t('common.loading')}</p>}

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
            <span className="mr-auto text-xs text-muted">{t('settings.unsaved_changes')}</span>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={reset}
              disabled={isSaving}
            >
              {t('common.reset')}
            </button>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => void save()}
              disabled={isSaving}
            >
              {isSaving ? t('common.saving') : t('settings.save_changes')}
            </button>
          </div>
        </div>
      )}
    </main>
  );
}

// --- sections ----------------------------------------------------------------

function GeneralSection({ draft, patch }: SectionProps) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col">
      <GroupLabel>{t('settings.groups.uploads_and_sessions')}</GroupLabel>
      <NumberRow
        id="max-upload"
        label={t('settings.general.max_upload.label')}
        hint={t('settings.general.max_upload.hint')}
        value={draft.maxImageSizeMb}
        min={1}
        max={1024}
        onChange={(maxImageSizeMb) => patch({ maxImageSizeMb })}
      />
      <NumberRow
        id="session-ttl"
        label={t('settings.general.session_ttl.label')}
        hint={t('settings.general.session_ttl.hint')}
        value={draft.sessionExpiryHours}
        min={1}
        max={8760}
        onChange={(sessionExpiryHours) => patch({ sessionExpiryHours })}
      />
      <NumberRow
        id="preview-size"
        label={t('settings.general.preview_size.label')}
        hint={t('settings.general.preview_size.hint')}
        value={draft.previewMaxSize}
        min={64}
        max={4096}
        step={64}
        onChange={(previewMaxSize) => patch({ previewMaxSize })}
      />

      <GroupLabel>{t('settings.groups.stacking_defaults')}</GroupLabel>
      <ToggleRow
        id="stacking-enabled"
        label={t('settings.general.stacking_enabled.label')}
        hint={t('settings.general.stacking_enabled.hint')}
        checked={draft.stackingEnabled}
        onChange={(stackingEnabled) => patch({ stackingEnabled })}
      />
      <NumberRow
        id="stacking-max"
        label={t('settings.general.stacking_max.label')}
        hint={t('settings.general.stacking_max.hint')}
        value={draft.stackingMaxFrames}
        min={2}
        max={1000}
        onChange={(stackingMaxFrames) => patch({ stackingMaxFrames })}
      />
      <SelectRow
        id="stacking-aligner"
        label={t('settings.general.stacking_aligner.label')}
        hint={t('settings.general.stacking_aligner.hint')}
        value={draft.stackingDetector}
        options={['orb', 'sift']}
        onChange={(stackingDetector) => patch({ stackingDetector })}
      />
      <SelectRow
        id="stacking-combine"
        label={t('settings.general.stacking_combine.label')}
        hint={t('settings.general.stacking_combine.hint')}
        value={draft.stackingCombinationDefault}
        options={['median', 'mean', 'sigma_clip']}
        onChange={(stackingCombinationDefault) => patch({ stackingCombinationDefault })}
      />
      <NumberRow
        id="stacking-sigma"
        label={t('settings.general.stacking_sigma.label')}
        hint={t('settings.general.stacking_sigma.hint')}
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
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-8">
      <TokenManager />

      <div className="flex flex-col">
        <GroupLabel>{t('settings.groups.callback_delivery')}</GroupLabel>
        <ListRow
          id="callback-allowlist"
          label={t('settings.webhooks.allowlist.label')}
          hint={t('settings.webhooks.allowlist.hint')}
          value={draft.astrodexCallbackUrls}
          placeholder="http://myastroboard.local/api/webhooks/enhanced-images"
          onChange={(astrodexCallbackUrls) => patch({ astrodexCallbackUrls })}
        />
        <NumberRow
          id="astrodex-retries"
          label={t('settings.webhooks.max_retries.label')}
          hint={t('settings.webhooks.max_retries.hint')}
          value={draft.astrodexMaxRetries}
          min={1}
          max={10}
          onChange={(astrodexMaxRetries) => patch({ astrodexMaxRetries })}
        />
        <NumberRow
          id="astrodex-delay"
          label={t('settings.webhooks.retry_delay.label')}
          hint={t('settings.webhooks.retry_delay.hint')}
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
  const { t } = useTranslation();
  return (
    <div className="flex flex-col">
      <GroupLabel>{t('settings.groups.network')}</GroupLabel>
      <ListRow
        id="cors-origins"
        label={t('settings.advanced.cors_origins.label')}
        hint={t('settings.advanced.cors_origins.hint')}
        value={draft.corsOrigins}
        placeholder="http://localhost:3000"
        onChange={(corsOrigins) => patch({ corsOrigins })}
      />

      <GroupLabel>{t('settings.groups.rate_limiting')}</GroupLabel>
      <ToggleRow
        id="rate-limit-enabled"
        label={t('settings.advanced.rate_limit_enabled.label')}
        hint={t('settings.advanced.rate_limit_enabled.hint')}
        checked={draft.rateLimitEnabled}
        onChange={(rateLimitEnabled) => patch({ rateLimitEnabled })}
      />
      <NumberRow
        id="rate-limit-per-minute"
        label={t('settings.advanced.rate_limit_per_minute.label')}
        hint={t('settings.advanced.rate_limit_per_minute.hint')}
        value={draft.rateLimitPerMinute}
        min={1}
        max={1000}
        onChange={(rateLimitPerMinute) => patch({ rateLimitPerMinute })}
      />
      <NumberRow
        id="max-concurrent-jobs"
        label={t('settings.advanced.max_concurrent_jobs.label')}
        hint={t('settings.advanced.max_concurrent_jobs.hint')}
        value={draft.maxConcurrentJobsPerIp}
        min={1}
        max={100}
        onChange={(maxConcurrentJobsPerIp) => patch({ maxConcurrentJobsPerIp })}
      />

      <GroupLabel>{t('settings.groups.logging')}</GroupLabel>
      <SelectRow
        id="log-file-level"
        label={t('settings.advanced.log_file_level.label')}
        hint={t('settings.advanced.log_file_level.hint')}
        value={draft.logLevel}
        options={LOG_LEVELS}
        onChange={(logLevel) => patch({ logLevel })}
      />
      <SelectRow
        id="log-console-level"
        label={t('settings.advanced.log_console_level.label')}
        hint={t('settings.advanced.log_console_level.hint')}
        value={draft.consoleLogLevel}
        options={LOG_LEVELS}
        onChange={(consoleLogLevel) => patch({ consoleLogLevel })}
      />
    </div>
  );
}

function LogsSection() {
  const { t } = useTranslation();
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
          {t('settings.logs.level_label')}
          <select
            className="field w-32 py-1.5"
            value={level}
            onChange={(event) => setLevel(event.target.value as LogLevel | '')}
          >
            <option value="">{t('settings.logs.level_all_option')}</option>
            {LOG_LEVELS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="btn btn-outline btn-sm" onClick={() => void refresh()}>
          {t('settings.logs.refresh')}
        </button>
        <button type="button" className="btn btn-outline btn-sm" onClick={() => void exportZip()}>
          {t('settings.logs.export_zip')}
        </button>
        <button
          type="button"
          className="btn btn-danger btn-sm"
          onClick={() => void handleClear()}
          onBlur={() => setConfirmClear(false)}
          disabled={busy}
        >
          {confirmClear ? t('settings.logs.confirm_clear') : t('settings.logs.clear')}
        </button>
      </div>

      {levels && (
        <p className="text-xs text-faint">
          {t('settings.logs.levels_hint', { file: levels.file, console: levels.console })}
        </p>
      )}

      <pre className="max-h-[440px] overflow-auto rounded-md border border-line bg-canvas p-3 font-mono text-[11px] leading-relaxed whitespace-pre text-muted">
        {isLoading && lines.length === 0
          ? t('common.loading')
          : lines.length === 0
            ? t('settings.logs.no_lines')
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
