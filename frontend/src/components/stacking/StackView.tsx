import { useEffect } from 'react';

import { useServerConfig } from '@/hooks/useServerConfig';
import { useStackProcessing } from '@/hooks/useStackProcessing';
import { useStackSettings } from '@/hooks/useStackSettings';
import { useTranslation } from '@/hooks/useTranslation';
import { apiClient } from '@/services/api';

import { StackFrameGrid } from './StackFrameGrid';
import { StackProgress } from './StackProgress';
import { StackResults } from './StackResults';
import { StackSettings } from './StackSettings';
import { StackUploadZone } from './StackUploadZone';

export interface StackViewProps {
  /** Hand the stacked composite session to the single-image editor. */
  onEnhanceComposite: (sessionId: string) => void;
}

const MIN_FRAMES = 2;

/** Multi-frame stacking: collect -> upload -> review the frame grid -> stack. */
export function StackView({ onEnhanceComposite }: StackViewProps) {
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
    addFiles,
    removePending,
    uploadFrames,
    toggleExclude,
    select,
    stack,
    reset,
  } = useStackProcessing(settings, stackingMaxFrames);

  const totalPicked = pending.length + uploaded.length;
  const hasWork = phase !== 'collecting' || totalPicked > 0;
  const selectedFrame = uploaded.find((frame) => frame.index === selected) ?? null;

  // Guard against a mis-swipe / mouse "back" losing an in-progress stack.
  useEffect(() => {
    if (!hasWork) {
      return;
    }
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [hasWork]);

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

  const showComposite = phase === 'done' && result?.stackedImageUrl && !selectedFrame;
  const previewSrc = showComposite
    ? result.stackedImageUrl
    : (selectedFrame?.thumbUrl ?? null);

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="flex flex-col gap-5">
        {phase === 'collecting' ? (
          <>
            <StackUploadZone
              compact={totalPicked > 0}
              maxSizeMb={maxImageSizeMb}
              onAddFiles={addFiles}
            />
            <StackFrameGrid
              pending={pending}
              uploaded={uploaded}
              selected={selected}
              interactive={false}
              onRemovePending={removePending}
              onSelect={select}
              onToggleExclude={() => {}}
            />
          </>
        ) : phase === 'uploading' ? (
          <StackProgress percent={progress.percent} currentStep="upload" />
        ) : (
          <>
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
              {phase === 'processing' && (
                <p className="absolute inset-x-0 bottom-3 text-center text-xs text-white/80">
                  {t('stacking.view.stacking_button')} {progress.percent}%
                </p>
              )}
            </div>

            <StackFrameGrid
              pending={pending}
              uploaded={uploaded}
              selected={selected}
              interactive={phase === 'reviewing' || phase === 'done'}
              onRemovePending={removePending}
              onSelect={select}
              onToggleExclude={(index, excluded) => void toggleExclude(index, excluded)}
            />
          </>
        )}
      </div>

      <aside className="flex flex-col gap-4">
        <section className="flex flex-col gap-2.5">
          <h2 className="eyebrow">{t('stacking.view.settings_heading')}</h2>
          <StackSettings settings={settings} onChange={setSettings} />
        </section>

        {(phase === 'collecting' || phase === 'uploading') && totalPicked > 0 && (
          <button
            type="button"
            className="btn btn-primary"
            disabled={phase === 'uploading' || totalPicked < MIN_FRAMES}
            onClick={() => void uploadFrames()}
          >
            {phase === 'uploading'
              ? t('stacking.view.uploading_button')
              : t('stacking.view.upload_n_frames', { count: totalPicked })}
          </button>
        )}

        {(phase === 'reviewing' || phase === 'done') && (
          <>
            {phase === 'reviewing' && (
              <StackUploadZone compact maxSizeMb={maxImageSizeMb} onAddFiles={addFiles} />
            )}
            <button
              type="button"
              className="btn btn-primary"
              disabled={activeCount < MIN_FRAMES}
              onClick={() => void stack()}
            >
              {phase === 'done'
                ? t('stacking.view.restack_n_frames', { count: activeCount })
                : t('stacking.view.stack_n_frames', { count: activeCount })}
            </button>
            <p className="text-xs text-faint">
              {t('stacking.view.review_hint', {
                total: uploaded.length,
                excluded: uploaded.length - activeCount,
              })}
            </p>
          </>
        )}

        {phase === 'done' && result && (
          <>
            <StackResults
              result={result}
              onEnhance={() => result.sessionId && onEnhanceComposite(result.sessionId)}
              onDownload={() => void handleDownload()}
            />
            <button type="button" className="btn btn-outline" onClick={reset}>
              {t('stacking.view.new_stack')}
            </button>
          </>
        )}

        {error && (
          <p className="rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-xs text-danger">
            {error}
          </p>
        )}
      </aside>
    </div>
  );
}
