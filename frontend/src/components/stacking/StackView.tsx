import { useStackProcessing } from '@/hooks/useStackProcessing';
import { useStackSettings } from '@/hooks/useStackSettings';
import { useTranslation } from '@/hooks/useTranslation';
import { apiClient } from '@/services/api';

import { StackProgress } from './StackProgress';
import { StackResults } from './StackResults';
import { StackSettings } from './StackSettings';
import { StackUploadZone } from './StackUploadZone';

export interface StackViewProps {
  /** Hand the stacked composite session to the single-image editor. */
  onEnhanceComposite: (sessionId: string) => void;
}

/** Multi-frame stacking workflow: upload -> configure -> process -> results. */
export function StackView({ onEnhanceComposite }: StackViewProps) {
  const { t } = useTranslation();
  const { settings, setSettings } = useStackSettings();
  const { frames, addFiles, run, result, phase, progress, error } = useStackProcessing(settings);

  const busy = phase === 'uploading' || phase === 'processing';
  const canStart = frames.length >= 2 && !busy;

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

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="flex flex-col gap-5">
        <StackUploadZone frames={frames} onAddFiles={addFiles} />

        {busy && <StackProgress percent={progress.percent} currentStep={progress.step} />}

        {result && phase === 'done' && (
          <StackResults
            result={result}
            onEnhance={() => result.sessionId && onEnhanceComposite(result.sessionId)}
            onDownload={() => void handleDownload()}
          />
        )}
      </div>

      <aside className="flex flex-col gap-4">
        <section className="flex flex-col gap-2.5">
          <h2 className="eyebrow">{t('stacking.view.settings_heading')}</h2>
          <StackSettings settings={settings} onChange={setSettings} />
        </section>
        <button
          type="button"
          className="btn btn-primary"
          disabled={!canStart}
          onClick={() => void run()}
        >
          {busy
            ? t('stacking.view.stacking_button')
            : t('stacking.view.stack_n_frames', { count: frames.length || '' })}
        </button>
        <p className="text-xs text-faint">{t('stacking.view.hint')}</p>
        {error && (
          <p className="rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-xs text-danger">
            {error}
          </p>
        )}
      </aside>
    </div>
  );
}
