import { useState } from 'react';

import { ActionButtons } from '@/components/ActionButtons';
import { DepthShiftViewer } from '@/components/DepthShiftViewer';
import { ImagePreview } from '@/components/ImagePreview';
import { PresetButtons } from '@/components/PresetButtons';
import { SavePresetDialog } from '@/components/SavePresetDialog';
import { SliderPanel } from '@/components/SliderPanel';
import { useDepthShift } from '@/hooks/useDepthShift';
import { useImageProcessing } from '@/hooks/useImageProcessing';
import { usePresets } from '@/hooks/usePresets';
import { apiClient } from '@/services/api';
import { DEFAULT_PARAMETERS, type EditorSession } from '@/types';

export interface AstroDexContext {
  imageId: string;
  callbackUrl: string;
  token: string;
}

export interface EditorViewProps {
  session: EditorSession;
  astrodexContext: AstroDexContext | null;
}

/** Main editing surface: preview + parameter panel + actions. */
export function EditorView({ session, astrodexContext }: EditorViewProps) {
  const { parameters, status, previewVersion, updateParameter, resetParameters, syncParameters } =
    useImageProcessing(session.sessionId);
  const { presets, applyPreset, activePreset, savePreset, deletePreset, clearActivePreset } =
    usePresets(session.sessionId);
  const depthShift = useDepthShift(session.sessionId);
  const [showDepthViewer, setShowDepthViewer] = useState(false);
  const [showSavePreset, setShowSavePreset] = useState(false);
  const [presetVersion, setPresetVersion] = useState(0);

  const aspectRatio = session.dimensions
    ? session.dimensions.width / session.dimensions.height
    : undefined;
  const originalUrl = apiClient.previewUrl(session.sessionId, { original: true });
  const processedUrl = apiClient.previewUrl(session.sessionId, {
    full: true,
    v: previewVersion + presetVersion,
  });

  async function handlePresetApply(presetId: string): Promise<void> {
    await applyPreset(presetId);
    const preset = presets.find((entry) => entry.presetId === presetId);
    if (preset) {
      syncParameters({ ...DEFAULT_PARAMETERS, ...preset.parameters });
    }
    setPresetVersion((version) => version + 1);
  }

  function handleParameterChange(key: keyof typeof parameters, value: number): void {
    clearActivePreset(); // manual edits diverge from any applied preset
    updateParameter(key, value);
  }

  function handleReset(): void {
    clearActivePreset();
    resetParameters();
  }

  async function handleDownload(): Promise<void> {
    const blob = await apiClient.downloadImage(session.sessionId);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `myastroshine_${session.sessionId.slice(0, 8)}.jpg`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function handleSendToAstroDex(): void {
    if (!astrodexContext) {
      return;
    }
    void apiClient.sendToAstroDex(
      session.sessionId,
      astrodexContext.imageId,
      astrodexContext.callbackUrl,
      astrodexContext.token,
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="flex flex-col gap-5">
        <ImagePreview
          originalUrl={originalUrl}
          processedUrl={processedUrl}
          histogram={session.histogram}
          aspectRatio={aspectRatio}
          isLoading={status === 'processing'}
          onDepthShiftClick={() => {
            if (depthShift.layerUrls.length === 0) {
              void depthShift.generate();
            }
            setShowDepthViewer(true);
          }}
        />
        {showDepthViewer && (
          <div className="flex flex-col gap-2">
            {depthShift.error ? (
              <p className="rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-xs text-danger">
                Depth shift failed: {depthShift.error}
              </p>
            ) : depthShift.layerUrls.length === 0 ? (
              <div className="grid h-40 place-items-center rounded-xl border border-hairline bg-surface text-xs text-faint">
                Generating depth map...
              </div>
            ) : (
              <DepthShiftViewer
                depthLayerUrls={depthShift.layerUrls}
                intensity={depthShift.intensity}
                aspectRatio={aspectRatio}
                onIntensityChange={depthShift.setIntensity}
                onClose={() => setShowDepthViewer(false)}
              />
            )}
          </div>
        )}
        <ActionButtons
          sessionId={session.sessionId}
          isProcessing={status === 'processing'}
          canSendToAstroDex={Boolean(astrodexContext)}
          onDownload={() => void handleDownload()}
          onSendToAstroDex={handleSendToAstroDex}
          onSavePreset={() => setShowSavePreset(true)}
        />
      </div>

      {showSavePreset && (
        <SavePresetDialog
          onSave={(name, description) => savePreset({ name, description, parameters })}
          onClose={() => setShowSavePreset(false)}
        />
      )}

      <aside className="flex flex-col gap-5">
        <section className="flex flex-col gap-2.5">
          <h2 className="eyebrow">Presets</h2>
          <PresetButtons
            presets={presets}
            activePreset={activePreset}
            onPresetApply={(id) => void handlePresetApply(id)}
            onPresetDelete={(id) => void deletePreset(id).catch(() => undefined)}
          />
        </section>
        <SliderPanel
          parameters={parameters}
          onParameterChange={handleParameterChange}
          onReset={handleReset}
          isProcessing={status === 'processing'}
        />
      </aside>
    </div>
  );
}
