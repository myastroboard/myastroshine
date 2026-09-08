import { useEffect, useState } from 'react';

import { useServerConfig } from '@/hooks/useServerConfig';
import { useStackProcessing } from '@/hooks/useStackProcessing';
import { useStackSettings } from '@/hooks/useStackSettings';
import { useTranslation } from '@/hooks/useTranslation';
import { apiClient } from '@/services/api';

import { StackCalibrationPanel } from './StackCalibrationPanel';
import { StackFrameGrid } from './StackFrameGrid';
import { StackProgress } from './StackProgress';
import { StackResults } from './StackResults';
import { StackSettings } from './StackSettings';
import { StackUploadZone } from './StackUploadZone';

export interface StackViewProps {
  /** Hand the stacked composite session to the single-image editor. */
  onEnhanceComposite: (sessionId: string) => void;
  /** Report whether a stack is in progress, so the shell can hide the mode toggle. */
  onWorkingChange?: (working: boolean) => void;
}

const MIN_FRAMES = 2;

type StackStep = 'frames' | 'calibration' | 'settings' | 'result';
const STEPS: StackStep[] = ['frames', 'calibration', 'settings', 'result'];

/**
 * Multi-frame stacking. Mirrors the single-image editor's shape: a clean upload
 * block first, then - once frames are in - a left workflow rail, a step
 * inspector, and a persistent preview with the frame grid.
 */
export function StackView({ onEnhanceComposite, onWorkingChange }: StackViewProps) {
  const { t } = useTranslation();
  const { stackingMaxFrames, maxImageSizeMb } = useServerConfig();
  const { settings, setSettings } = useStackSettings();
  const {
    phase,
    pending,
    uploaded,
    selected,
    activeCount,
    result,
    progress,
    error,
    calibration,
    addFiles,
    removePending,
    uploadFrames,
    toggleExclude,
    addCalibrationFiles,
    clearCalibrationKind,
    select,
    stack,
    reset,
  } = useStackProcessing(settings, stackingMaxFrames);

  const [step, setStep] = useState<StackStep>('frames');

  const inEditor = phase === 'reviewing' || phase === 'processing' || phase === 'done';
  const busy = phase === 'processing';
  const hasWork = phase !== 'collecting' || pending.length > 0;
  const selectedFrame = uploaded.find((frame) => frame.index === selected) ?? null;
  const excludedCount = uploaded.filter((frame) => frame.excluded).length;
  const calibrationCount = Object.values(calibration.frames).reduce((sum, n) => sum + n, 0);

  useEffect(() => onWorkingChange?.(inEditor || pending.length > 0), [inEditor, pending.length, onWorkingChange]);

  // Guard against a mis-swipe / mouse "back" losing an in-progress stack.
  useEffect(() => {
    if (!hasWork) {
      return undefined;
    }
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [hasWork]);

  // Follow the workflow: land on Result when a stack finishes, back to Frames on reset.
  useEffect(() => {
    if (phase === 'done') {
      setStep('result');
    } else if (phase === 'collecting') {
      setStep('frames');
    } else if (phase === 'reviewing') {
      setStep((current) => (current === 'result' ? 'frames' : current));
    }
  }, [phase]);

  async function handleDownload(): Promise<void> {
    if (!result?.sessionId) {
      return;
    }
    const blob = await apiClient.downloadImage(result.sessionId);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `myastroshine_stack_${result.stackId.slice(0, 8)}.jpg`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  const errorNote = error ? (
    <p className="rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-xs text-danger">
      {error}
    </p>
  ) : null;

  // -- pre-upload: just the upload block, like the single-image screen ----------

  if (!inEditor && phase !== 'uploading') {
    return (
      <div className="mx-auto flex w-full max-w-xl flex-col gap-4">
        <StackUploadZone
          compact={pending.length > 0}
          maxSizeMb={maxImageSizeMb}
          onAddFiles={addFiles}
        />
        {pending.length > 0 && (
          <>
            <button
              type="button"
              className="btn btn-primary"
              disabled={pending.length < MIN_FRAMES}
              onClick={() => void uploadFrames()}
            >
              {t('stacking.view.upload_n_frames', { count: pending.length })}
            </button>
            <StackFrameGrid
              pending={pending}
              uploaded={[]}
              selected={null}
              interactive={false}
              onRemovePending={removePending}
              onSelect={() => {}}
              onToggleExclude={() => {}}
            />
          </>
        )}
        {errorNote}
      </div>
    );
  }

  if (phase === 'uploading') {
    return (
      <div className="mx-auto w-full max-w-xl">
        <StackProgress percent={progress.percent} currentStep="upload" />
      </div>
    );
  }

  // -- editor shell -----------------------------------------------------------

  const previewSrc =
    phase === 'done' && result?.stackedImageUrl && !selectedFrame
      ? result.stackedImageUrl
      : (selectedFrame?.thumbUrl ?? null);

  const ctaLabel = busy
    ? `${t('stacking.view.stacking_button')} ${progress.percent}%`
    : pending.length > 0
      ? t('stacking.view.upload_more', { count: pending.length })
      : phase === 'done'
        ? t('stacking.view.restack_n_frames', { count: activeCount })
        : t('stacking.view.stack_n_frames', { count: activeCount });

  const onCta = pending.length > 0 ? () => void uploadFrames() : () => void stack();
  const ctaDisabled = busy || (pending.length === 0 && activeCount < MIN_FRAMES);

  return (
    <div className="grid gap-5 lg:grid-cols-[12.5rem_19rem_minmax(0,1fr)] lg:items-start">
      <div className="panel flex flex-col gap-3">
        <button
          type="button"
          className="btn btn-ghost btn-sm self-start"
          disabled={busy}
          onClick={reset}
        >
          <svg viewBox="0 0 12 12" className="h-3 w-3 stroke-current" fill="none" aria-hidden>
            <path d="M7.5 2 3 6l4.5 4" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          {t('stacking.view.new_stack')}
        </button>

        <nav
          aria-label={t('stacking.rail.aria_label')}
          className="flex gap-1.5 overflow-x-auto pb-1 lg:flex-col lg:gap-0.5 lg:overflow-visible lg:pb-0"
        >
          {STEPS.map((id, index) => {
            const active = id === step;
            const locked = id === 'result' && phase !== 'done';
            const marked =
              (id === 'frames' && excludedCount > 0) ||
              (id === 'calibration' && calibrationCount > 0);
            return (
              <button
                key={id}
                type="button"
                aria-current={active ? 'step' : undefined}
                disabled={locked}
                onClick={() => setStep(id)}
                className={`group flex shrink-0 items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-accent lg:w-full ${
                  active
                    ? 'bg-accent-wash text-ink'
                    : locked
                      ? 'text-ghost'
                      : 'text-muted hover:bg-hover hover:text-ink'
                }`}
              >
                <span
                  className={`grid h-5 w-5 shrink-0 place-items-center rounded-full border text-[11px] font-semibold tabular-nums ${
                    active ? 'border-accent/60 text-accent' : 'border-line-strong text-faint'
                  }`}
                >
                  {index + 1}
                </span>
                <span className="flex-1 truncate">{t(`stacking.rail.${id}`)}</span>
                {marked && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" aria-hidden />}
              </button>
            );
          })}
        </nav>

        <button
          type="button"
          className="btn btn-primary"
          disabled={ctaDisabled}
          onClick={onCta}
        >
          {ctaLabel}
        </button>
        {errorNote}
      </div>

      <div className="flex flex-col gap-4">
        {step === 'frames' && (
          <div className="panel flex flex-col gap-3">
            <p className="text-xs text-muted">
              {t('stacking.view.frames_summary', {
                total: uploaded.length,
                excluded: excludedCount,
              })}
            </p>
            <StackUploadZone compact maxSizeMb={maxImageSizeMb} onAddFiles={addFiles} />
            <p className="text-[11px] text-faint">
              {t('stacking.view.review_hint', {
                total: uploaded.length,
                excluded: excludedCount,
              })}
            </p>
          </div>
        )}

        {step === 'calibration' && (
          <StackCalibrationPanel
            calibration={calibration}
            cosmeticCorrection={settings.cosmeticCorrection}
            disabled={busy}
            onAdd={(kind, files) => void addCalibrationFiles(kind, files)}
            onClear={(kind) => void clearCalibrationKind(kind)}
            onToggleCosmetic={(value) => setSettings({ ...settings, cosmeticCorrection: value })}
          />
        )}

        {step === 'settings' && <StackSettings settings={settings} onChange={setSettings} />}

        {step === 'result' &&
          (result ? (
            <StackResults
              result={result}
              onEnhance={() => result.sessionId && onEnhanceComposite(result.sessionId)}
              onDownload={() => void handleDownload()}
            />
          ) : (
            <p className="panel text-xs text-faint">{t('stacking.view.result_pending')}</p>
          ))}
      </div>

      <div className="flex flex-col gap-4 lg:sticky lg:top-20 lg:self-start">
        <div className="panel relative grid min-h-[16rem] place-items-center overflow-hidden bg-black p-0">
          {previewSrc && (
            <img
              src={previewSrc}
              alt={t('stacking.results.composite_alt')}
              className="max-h-[70vh] w-full object-contain"
            />
          )}
          {phase === 'done' && selectedFrame && (
            <button
              type="button"
              onClick={() => select(selectedFrame.index)}
              className="absolute left-3 top-3 rounded-md border border-white/10 bg-black/60 px-3 py-1.5 text-xs text-white/85 backdrop-blur-sm transition-colors hover:bg-black/80"
            >
              {t('stacking.view.back_to_composite')}
            </button>
          )}
          {busy && (
            <p className="absolute inset-x-0 bottom-3 text-center text-xs text-white/80">
              {t('stacking.view.stacking_button')} {progress.percent}%
            </p>
          )}
        </div>

        <StackFrameGrid
          pending={[]}
          uploaded={uploaded}
          selected={selected}
          interactive={phase === 'reviewing' || phase === 'done'}
          onRemovePending={removePending}
          onSelect={select}
          onToggleExclude={(index, excluded) => void toggleExclude(index, excluded)}
        />
      </div>
    </div>
  );
}
