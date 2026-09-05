import { useEffect, useState } from 'react';

import { DepthShiftViewer } from '@/components/DepthShiftViewer';
import { EditorInspector } from '@/components/EditorInspector';
import { EditorRail } from '@/components/EditorRail';
import { ImagePreview } from '@/components/ImagePreview';
import { SavePresetDialog } from '@/components/SavePresetDialog';
import { useAutoAstro } from '@/hooks/useAutoAstro';
import { useDepthShift } from '@/hooks/useDepthShift';
import { useImageProcessing } from '@/hooks/useImageProcessing';
import { usePresets } from '@/hooks/usePresets';
import { useStarMask } from '@/hooks/useStarMask';
import { useTranslation } from '@/hooks/useTranslation';
import { apiClient } from '@/services/api';
import {
  DEFAULT_GEOMETRY,
  DEFAULT_PARAMETERS,
  geometryEquals,
  isDefaultGeometry,
  type CurveChannel,
  type CurvePoint,
  type Dimensions,
  type EditorSession,
  type EditorStepId,
  type FocusPoint,
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

/** Main editing surface: workflow rail + step inspector + persistent preview. */
export function EditorView({ session, astrodexContext }: EditorViewProps) {
  const { t } = useTranslation();
  const {
    parameters,
    status,
    previewVersion,
    updateParameter,
    updateChannelCurve,
    applyGeometry,
    resetParameters,
    resetCurves,
    resetKeys,
    syncParameters,
  } = useImageProcessing(session.sessionId);
  const { presets, applyPreset, activePreset, savePreset, deletePreset, clearActivePreset } =
    usePresets(session.sessionId);
  const depthShift = useDepthShift(session.sessionId);
  const starMask = useStarMask(session.sessionId);
  const autoAstro = useAutoAstro(session.sessionId);
  const { detect: detectStars } = starMask;

  const [activeStep, setActiveStep] = useState<EditorStepId>('start');
  const [showDepthViewer, setShowDepthViewer] = useState(false);
  const [showSavePreset, setShowSavePreset] = useState(false);
  const [presetVersion, setPresetVersion] = useState(0);
  const [starMaskEnabled, setStarMaskEnabled] = useState(false);
  const [focalPoint, setFocalPoint] = useState<FocusPoint | null>(null);
  const [pickingFocalPoint, setPickingFocalPoint] = useState(false);
  const [framingGeom, setFramingGeom] = useState<GeometryParameters>(parameters.geometry);
  const [framingRatioFrac, setFramingRatioFrac] = useState<number | null>(null);

  // Keep the framing draft in step with geometry applied elsewhere (a preset,
  // Auto Astro, or a global reset). Draft-only edits don't change the reference,
  // so this doesn't clobber an in-progress crop.
  useEffect(() => {
    setFramingGeom(parameters.geometry);
  }, [parameters.geometry]);

  function handleStarMaskToggle(enabled: boolean): void {
    setStarMaskEnabled(enabled);
    if (enabled) {
      void detectStars(parameters.starSensitivity, parameters.starMaxSize);
    } else {
      starMask.clear();
    }
  }

  // Re-run detection (debounced) whenever the star controls change while the
  // mask overlay is showing, so it tracks the same sliders it previews for.
  useEffect(() => {
    if (!starMaskEnabled) {
      return undefined;
    }
    const timeout = setTimeout(() => {
      void detectStars(parameters.starSensitivity, parameters.starMaxSize);
    }, 500);
    return () => clearTimeout(timeout);
  }, [starMaskEnabled, parameters.starSensitivity, parameters.starMaxSize, detectStars]);

  const framingAvailable = Boolean(session.dimensions);
  const framingDirty = !geometryEquals(framingGeom, parameters.geometry);
  const framingActive = activeStep === 'frame' && framingAvailable;

  const geometryChanged = !isDefaultGeometry(parameters.geometry);
  const aspectRatio = displayedAspect(session.dimensions, parameters.geometry);
  const version = previewVersion + presetVersion;
  const originalUrl = geometryChanged
    ? apiClient.previewUrl(session.sessionId, { original: true, geometry: true, v: version })
    : apiClient.previewUrl(session.sessionId, { original: true });
  const processedUrl = apiClient.previewUrl(session.sessionId, { full: true, v: version });

  function handleStepChange(next: EditorStepId): void {
    // Leaving the Framing step with an uncommitted crop commits it.
    if (activeStep === 'frame' && next !== 'frame' && framingDirty) {
      applyGeometry(framingGeom);
      setPresetVersion((v) => v + 1);
    }
    if (activeStep === 'depth' && next !== 'depth') {
      setPickingFocalPoint(false);
    }
    setActiveStep(next);
  }

  function handleFramingApply(): void {
    applyGeometry(framingGeom);
    setPresetVersion((v) => v + 1);
  }

  function handleFramingReset(): void {
    setFramingGeom(DEFAULT_GEOMETRY);
    setFramingRatioFrac(null);
    if (!isDefaultGeometry(parameters.geometry)) {
      applyGeometry(DEFAULT_GEOMETRY);
      setPresetVersion((v) => v + 1);
    }
  }

  async function handlePresetApply(presetId: string): Promise<void> {
    await applyPreset(presetId);
    const preset = presets.find((entry) => entry.presetId === presetId);
    if (preset) {
      // A preset is a look, not a composition - keep the current framing
      // (the backend's preset-apply route preserves geometry the same way).
      syncParameters({
        ...DEFAULT_PARAMETERS,
        ...preset.parameters,
        geometry: parameters.geometry,
      });
    }
    setPresetVersion((v) => v + 1);
  }

  async function handleAutoAstro(): Promise<void> {
    clearActivePreset();
    const result = await autoAstro.apply();
    if (result) {
      // Auto Astro proposes tone/star settings only - carry the framing over.
      syncParameters({
        ...DEFAULT_PARAMETERS,
        ...result.parameters,
        geometry: parameters.geometry,
      });
      setPresetVersion((v) => v + 1);
    }
  }

  function handleParameterChange(key: SliderParameterKey, value: number): void {
    clearActivePreset(); // manual edits diverge from any applied preset
    updateParameter(key, value);
  }

  function handleResetAll(): void {
    clearActivePreset();
    resetParameters();
  }

  function handleResetSection(keys: SliderParameterKey[]): void {
    clearActivePreset();
    resetKeys(keys);
  }

  function handleResetCurves(): void {
    clearActivePreset();
    resetCurves();
  }

  function handleCurveChange(channel: CurveChannel, points: CurvePoint[]): void {
    clearActivePreset(); // manual edits diverge from any applied preset
    updateChannelCurve(channel, points);
  }

  function handleFocalPointPick(point: FocusPoint): void {
    setFocalPoint(point);
    setPickingFocalPoint(false);
    // Regenerate eagerly so a change is reflected right away if the viewer is
    // already open, and is ready instantly the next time it's opened.
    void depthShift.generate(7, point);
  }

  function handleClearFocalPoint(): void {
    setFocalPoint(null);
    void depthShift.generate(7);
  }

  function handleOpenDepthViewer(): void {
    if (depthShift.layerUrls.length === 0) {
      void depthShift.generate(7, focalPoint ?? undefined);
    }
    setShowDepthViewer(true);
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

  const isProcessing = status === 'processing';

  return (
    <div className="grid gap-5 lg:grid-cols-[10.5rem_19rem_minmax(0,1fr)] lg:items-start">
      <EditorRail
        activeStep={activeStep}
        onStepChange={handleStepChange}
        parameters={parameters}
        focalPoint={focalPoint}
      />

      <EditorInspector
        activeStep={activeStep}
        onStepChange={handleStepChange}
        parameters={parameters}
        onParameterChange={handleParameterChange}
        onResetSection={handleResetSection}
        onCurveChange={handleCurveChange}
        onResetCurves={handleResetCurves}
        isProcessing={isProcessing}
        start={{
          onAutoAstro: () => void handleAutoAstro(),
          autoAstroLoading: autoAstro.isLoading,
          autoAstroError: autoAstro.error,
          presets,
          activePreset,
          onPresetApply: (id) => void handlePresetApply(id),
          onPresetDelete: (id) => void deletePreset(id).catch(() => undefined),
          onResetAll: handleResetAll,
        }}
        framing={{
          available: framingAvailable,
          dimensions: session.dimensions ?? { width: 0, height: 0 },
          geometry: framingGeom,
          ratioFrac: framingRatioFrac,
          dirty: framingDirty,
          onGeometryChange: setFramingGeom,
          onRatioFracChange: setFramingRatioFrac,
          onApply: handleFramingApply,
          onReset: handleFramingReset,
        }}
        stars={{
          enabled: starMaskEnabled,
          onToggle: handleStarMaskToggle,
          sourceCount: starMask.sourceCount,
          loading: starMask.isLoading,
        }}
        depth={{
          focalPoint,
          picking: pickingFocalPoint,
          onTogglePick: () => setPickingFocalPoint((picking) => !picking),
          onClear: handleClearFocalPoint,
          onOpenViewer: handleOpenDepthViewer,
          error: depthShift.error,
        }}
        exportActions={{
          canSendToAstroDex: Boolean(astrodexContext),
          onDownload: () => void handleDownload(),
          onSendToAstroDex: handleSendToAstroDex,
          onSaveAsPreset: () => setShowSavePreset(true),
        }}
      />

      <div className="flex flex-col gap-4 lg:sticky lg:top-20 lg:self-start">
        <ImagePreview
          originalUrl={originalUrl}
          processedUrl={processedUrl}
          histogram={session.histogram}
          aspectRatio={aspectRatio}
          isLoading={isProcessing}
          framing={
            framingActive && session.dimensions
              ? {
                  imageUrl: apiClient.previewUrl(session.sessionId, { original: true }),
                  dimensions: session.dimensions,
                  geometry: framingGeom,
                  ratioFrac: framingRatioFrac,
                  onGeometryChange: setFramingGeom,
                }
              : null
          }
          starMaskOverlay={starMaskEnabled && !framingActive ? starMask.stars : null}
          focalPoint={framingActive ? null : focalPoint}
          pickingFocalPoint={activeStep === 'depth' && pickingFocalPoint}
          onFocalPointPick={handleFocalPointPick}
        />

        {showDepthViewer && (
          <div className="flex flex-col gap-2">
            {depthShift.error ? (
              <p className="rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-xs text-danger">
                {t('editor.depth_shift_failed', { error: depthShift.error })}
              </p>
            ) : depthShift.layerUrls.length === 0 ? (
              <div className="grid h-40 place-items-center rounded-xl border border-hairline bg-surface text-xs text-faint">
                {t('editor.generating_depth_map')}
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
      </div>

      {showSavePreset && (
        <SavePresetDialog
          onSave={(name, description) => savePreset({ name, description, parameters })}
          onClose={() => setShowSavePreset(false)}
        />
      )}
    </div>
  );
}
