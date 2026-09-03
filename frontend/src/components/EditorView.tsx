import { useState } from 'react';

import { ActionButtons } from '@/components/ActionButtons';
import { DepthShiftViewer } from '@/components/DepthShiftViewer';
import { ImagePreview } from '@/components/ImagePreview';
import { PresetButtons } from '@/components/PresetButtons';
import { SliderPanel } from '@/components/SliderPanel';
import { useDepthShift } from '@/hooks/useDepthShift';
import { useImageProcessing } from '@/hooks/useImageProcessing';
import { usePresets } from '@/hooks/usePresets';
import { apiClient } from '@/services/api';
import type { UploadResponse } from '@/types';

export interface AstroDexContext {
  imageId: string;
  callbackUrl: string;
  token: string;
}

export interface EditorViewProps {
  session: UploadResponse;
  astrodexContext: AstroDexContext | null;
}

/** Main editing surface: preview + parameter panel + actions. */
export function EditorView({ session, astrodexContext }: EditorViewProps) {
  const { parameters, status, updateParameter, resetParameters } = useImageProcessing(session.sessionId);
  const { presets, applyPreset, activePreset } = usePresets(session.sessionId);
  const depthShift = useDepthShift(session.sessionId);
  const [showDepthViewer, setShowDepthViewer] = useState(false);

  const originalUrl = apiClient.previewUrl(session.sessionId);
  const processedUrl = apiClient.previewUrl(session.sessionId, true);

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
      parameters,
      astrodexContext.callbackUrl,
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <div className="flex flex-col gap-4">
        <ImagePreview
          originalUrl={originalUrl}
          processedUrl={processedUrl}
          histogram={session.histogram}
          isLoading={status === 'processing'}
          onDepthShiftClick={() => {
            void depthShift.generate();
            setShowDepthViewer(true);
          }}
        />
        {showDepthViewer && depthShift.layerUrls.length > 0 && (
          <DepthShiftViewer
            depthLayerUrls={depthShift.layerUrls}
            intensity={depthShift.intensity}
            onIntensityChange={depthShift.setIntensity}
            onClose={() => setShowDepthViewer(false)}
          />
        )}
        <ActionButtons
          sessionId={session.sessionId}
          isProcessing={status === 'processing'}
          canSendToAstroDex={Boolean(astrodexContext)}
          onDownload={() => void handleDownload()}
          onSendToAstroDex={handleSendToAstroDex}
          onSavePreset={() => undefined}
        />
      </div>

      <aside className="flex flex-col gap-4">
        <PresetButtons presets={presets} activePreset={activePreset} onPresetApply={applyPreset} />
        <SliderPanel
          parameters={parameters}
          onParameterChange={updateParameter}
          onReset={resetParameters}
          isProcessing={status === 'processing'}
        />
      </aside>
    </div>
  );
}
