import { useState } from 'react';

import { ActionButtons } from '@/components/ActionButtons';
import { CropTool } from '@/components/CropTool';
import { DepthShiftViewer } from '@/components/DepthShiftViewer';
import { ImagePreview } from '@/components/ImagePreview';
import { PresetButtons } from '@/components/PresetButtons';
import { SavePresetDialog } from '@/components/SavePresetDialog';
import { SliderPanel } from '@/components/SliderPanel';
import { useDepthShift } from '@/hooks/useDepthShift';
import { useImageProcessing } from '@/hooks/useImageProcessing';
import { usePresets } from '@/hooks/usePresets';
import { apiClient } from '@/services/api';
import {
  DEFAULT_PARAMETERS,
  isDefaultGeometry,
  type Dimensions,
  type EditorSession,
  type GeometryParameters,
  type SliderParameterKey,
} from '@/types';

export interface AstroDexContext {
  imageId: string;
  callbackUrl: string;
  token: string;
}

export interface EditorViewProps {
  session: EditorSession;
  astrodexContext: AstroDexContext | null;
}

/** Aspect ratio of the enhanced result, given the framing. */
function displayedAspect(dimensions: Dimensions | undefined, geometry: GeometryParameters): number {
  if (!dimensions) {
    return 16 / 9;
  }
  const odd = geometry.rotateQuarters % 2 === 1;
  const width = (odd ? dimensions.height : dimensions.width) * geometry.cropW;
  const height = (odd ? dimensions.width : dimensions.height) * geometry.cropH;
  return width / height;
}

/** Main editing surface: preview + parameter panel + actions. */
export function EditorView({ session, astrodexContext }: EditorViewProps) {
  const { parameters, status, previewVersion, updateParameter, applyGeometry, resetParameters, syncParameters } =
    useImageProcessing(session.sessionId);
  const { presets, applyPreset, activePreset, savePreset, deletePreset, clearActivePreset } =
    usePresets(session.sessionId);
  const depthShift = useDepthShift(session.sessionId);
  const [showDepthViewer, setShowDepthViewer] = useState(false);
  const [showSavePreset, setShowSavePreset] = useState(false);
  const [showCrop, setShowCrop] = useState(false);
  const [presetVersion, setPresetVersion] = useState(0);

  const geometryChanged = !isDefaultGeometry(parameters.geometry);
  const aspectRatio = displayedAspect(session.dimensions, parameters.geometry);
  const version = previewVersion + presetVersion;
  const originalUrl = geometryChanged
    ? apiClient.previewUrl(session.sessionId, { original: true, geometry: true, v: version })
    : apiClient.previewUrl(session.sessionId, { original: true });
  const processedUrl = apiClient.previewUrl(session.sessionId, { full: true, v: version });

  async function handlePresetApply(presetId: string): Promise<void> {
    await applyPreset(presetId);
    const preset = presets.find((entry) => entry.presetId === presetId);
    if (preset) {
      syncParameters({ ...DEFAULT_PARAMETERS, ...preset.parameters });
    }
    setPresetVersion((v) => v + 1);
  }

  function handleParameterChange(key: SliderParameterKey, value: number): void {
    clearActivePreset(); // manual edits diverge from any applied preset
    updateParameter(key, value);
  }

  function handleReset(): void {
    clearActivePreset();
    resetParameters();
  }

  function handleCropDone(geometry: GeometryParameters): void {
    setShowCrop(false);
    applyGeometry(geometry);
    setPresetVersion((v) => v + 1);
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
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className={`btn btn-sm ${geometryChanged ? 'btn-primary' : 'btn-outline'}`}
            disabled={!session.dimensions || status === 'processing'}
            onClick={() => setShowCrop(true)}
          >
            Crop &amp; rotate
          </button>
          <ActionButtons
            sessionId={session.sessionId}
            isProcessing={status === 'processing'}
            canSendToAstroDex={Boolean(astrodexContext)}
            onDownload={() => void handleDownload()}
            onSendToAstroDex={handleSendToAstroDex}
            onSavePreset={() => setShowSavePreset(true)}
          />
        </div>
      </div>

      {showCrop && session.dimensions && (
        <CropTool
          imageUrl={apiClient.previewUrl(session.sessionId, { original: true })}
          dimensions={session.dimensions}
          geometry={parameters.geometry}
          onDone={handleCropDone}
          onCancel={() => setShowCrop(false)}
        />
      )}

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
