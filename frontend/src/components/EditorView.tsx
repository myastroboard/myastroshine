import { useEffect, useRef, useState } from 'react';

import { CaptureInfoPanel } from '@/components/CaptureInfoPanel';
import { DepthShiftViewer } from '@/components/DepthShiftViewer';
import { EditorInspector } from '@/components/EditorInspector';
import { EditorRail } from '@/components/EditorRail';
import { ImagePreview } from '@/components/ImagePreview';
import { MilestoneTimeline } from '@/components/MilestoneTimeline';
import { SavePresetDialog } from '@/components/SavePresetDialog';
import { useAstroDexIntegration } from '@/hooks/useAstroDexIntegration';
import { useAutoAstro } from '@/hooks/useAutoAstro';
import { useCaptureInfo } from '@/hooks/useCaptureInfo';
import { useDepthShift } from '@/hooks/useDepthShift';
import { useImageProcessing } from '@/hooks/useImageProcessing';
import { useMilestones, type Milestone } from '@/hooks/useMilestones';
import { usePresets } from '@/hooks/usePresets';
import { useServerConfig } from '@/hooks/useServerConfig';
import { useStarMask } from '@/hooks/useStarMask';
import { useTranslation } from '@/hooks/useTranslation';
import { apiClient } from '@/services/api';
import {
  DEFAULT_GEOMETRY,
  DEFAULT_PARAMETERS,
  geometryEquals,
  hasEdits,
  isDefaultGeometry,
  parametersEqual,
  type CurveChannel,
  type CurvePoint,
  type Dimensions,
  type EditorSession,
  type EditorStepId,
  type FocusPoint,
  type GeometryParameters,
  type ProcessingParameters,
  type SliderParameterKey,
} from '@/types';

export interface EditorViewProps {
  session: EditorSession;
  /** Leave the editor and go back to the upload screen. */
  onExit: () => void;
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

function focusPointsEqual(a: FocusPoint | null, b: FocusPoint | null): boolean {
  if (a === null || b === null) {
    return a === b;
  }
  return a.x === b.x && a.y === b.y;
}

/** Drop a trailing image extension (`.jpg`, `.tiff`, `.cr2`, ...) from a name. */
function stripImageExtension(name: string): string {
  return name.replace(/\.[A-Za-z0-9]{1,5}$/, '');
}

/** Default name (no extension) for the exported result: the uploaded file's base
 * name, or the AstroDex object, with a `_myastroshine` suffix - falling back to a
 * short session tag when there is no source name (a stacked composite). */
function defaultExportName(session: EditorSession): string {
  if (session.originalFilename) {
    return `${stripImageExtension(session.originalFilename)}_myastroshine`;
  }
  if (session.astrodex?.objectName) {
    return `${session.astrodex.objectName}_myastroshine`;
  }
  return `myastroshine_${session.sessionId.slice(0, 8)}`;
}

/** Main editing surface: workflow rail + step inspector + persistent preview. */
export function EditorView({ session, onExit }: EditorViewProps) {
  const { t } = useTranslation();
  const {
    parameters,
    status,
    progress,
    currentStep,
    previewVersion,
    sliderRevert,
    revertSlider,
    updateParameter,
    updateStarRemovalEngine,
    updateDenoiseEngine,
    updateStackParameter,
    updateChannelCurve,
    applyGeometry,
    trackJob,
    resetParameters,
    resetStack,
    resetCurves,
    resetKeys,
    syncParameters,
    restoreParameters,
  } = useImageProcessing(session.sessionId);
  const { presets, applyPreset, activePreset, savePreset, deletePreset, clearActivePreset } =
    usePresets(session.sessionId);
  const depthShift = useDepthShift(session.sessionId);
  const serverConfig = useServerConfig();
  const starMask = useStarMask(session.sessionId);
  const autoAstro = useAutoAstro(session.sessionId);
  const captureInfo = useCaptureInfo(session.sessionId, Boolean(session.isStack));
  const astrodex = useAstroDexIntegration();
  const { detect: detectStars } = starMask;

  const [activeStep, setActiveStep] = useState<EditorStepId>(session.isStack ? 'stack' : 'start');
  const [showDepthViewer, setShowDepthViewer] = useState(false);
  const [showSavePreset, setShowSavePreset] = useState(false);
  const [presetVersion, setPresetVersion] = useState(0);
  const [starMaskEnabled, setStarMaskEnabled] = useState(false);
  const [focalPoint, setFocalPoint] = useState<FocusPoint | null>(null);
  const [pickingFocalPoint, setPickingFocalPoint] = useState(false);
  const [framingGeom, setFramingGeom] = useState<GeometryParameters>(parameters.geometry);
  const [framingRatioFrac, setFramingRatioFrac] = useState<number | null>(null);
  const [confirmExit, setConfirmExit] = useState(false);
  // The edit state that was last sent back to AstroDex - once it matches the
  // current state the work is delivered, so the unsaved-changes guard stands down.
  const [delivered, setDelivered] = useState<{
    parameters: ProcessingParameters;
    focalPoint: FocusPoint | null;
  } | null>(null);

  const {
    milestones,
    activeId: activeMilestoneId,
    capture: captureMilestone,
  } = useMilestones(session.sessionId, parameters, focalPoint);

  const editState = useRef({ parameters, focalPoint });
  editState.current = { parameters, focalPoint };

  const deliveredToAstrodex =
    delivered !== null &&
    !astrodex.error &&
    parametersEqual(parameters, delivered.parameters) &&
    focusPointsEqual(focalPoint, delivered.focalPoint);

  const dirty = (hasEdits(parameters) || focalPoint !== null) && !deliveredToAstrodex;

  // Warn before a full-page navigation (mobile edge-swipe back, reload, tab
  // close) drops unsaved edits - there is no server-side draft to recover.
  useEffect(() => {
    if (!dirty) {
      return undefined;
    }
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  function handleExitRequest(): void {
    if (dirty) {
      setConfirmExit(true);
    } else {
      onExit();
    }
  }

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
  // A stacked composite arrives without known dimensions - let ImagePreview read
  // the real aspect ratio off the loaded image instead of forcing 16:9.
  const previewAspectRatio = session.dimensions ? aspectRatio : undefined;
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
    const job = await applyPreset(presetId);
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
    // Follow the job to completion so the preview refetches when the result is
    // actually ready - on the queue the job is still running when this returns.
    trackJob(job);
  }

  async function handleAutoAstro(): Promise<void> {
    clearActivePreset();
    const result = await autoAstro.apply();
    if (result) {
      // Auto Astro proposes tone/star/gradient/white-balance/denoise settings
      // only - carry the framing over.
      syncParameters({
        ...DEFAULT_PARAMETERS,
        ...result.parameters,
        geometry: parameters.geometry,
      });
      trackJob(result);
    }
  }

  function handleParameterChange(key: SliderParameterKey, value: number): void {
    clearActivePreset(); // manual edits diverge from any applied preset
    updateParameter(key, value);
  }

  function handleSliderRevert(): void {
    clearActivePreset();
    revertSlider();
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

  function handleMilestoneRestore(milestone: Milestone): void {
    clearActivePreset();
    setFocalPoint(milestone.focalPoint);
    restoreParameters(milestone.parameters); // sets state + reprocesses
    setPresetVersion((v) => v + 1); // cache-bust the preview URLs
    // Keep an already-open depth viewer in step with the restored focal point.
    if (depthShift.layerUrls.length > 0) {
      void depthShift.generate(7, milestone.focalPoint ?? undefined);
    }
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

  async function handleDownload(filename: string): Promise<void> {
    const blob = await apiClient.downloadImage(session.sessionId);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    const base = stripImageExtension(filename.trim()) || defaultExportName(session);
    anchor.download = `${base}.jpg`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function handleReturnToAstrodex(): Promise<void> {
    if (!session.astrodex) {
      return;
    }
    const ok = await astrodex.returnImage(session.sessionId);
    if (ok) {
      setDelivered(editState.current);
    }
  }

  const isProcessing = status === 'processing';

  return (
    <div className="grid gap-5 lg:grid-cols-[12.5rem_19rem_minmax(0,1fr)] lg:items-start">
      <div className="panel flex flex-col gap-3">
        <button
          type="button"
          className="btn btn-ghost btn-sm self-start"
          onClick={handleExitRequest}
        >
          <svg viewBox="0 0 12 12" className="h-3 w-3 stroke-current" fill="none" aria-hidden>
            <path
              d="M7.5 2 3 6l4.5 4"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          {t('editor.new_photo')}
        </button>
        <EditorRail
          activeStep={activeStep}
          onStepChange={handleStepChange}
          parameters={parameters}
          focalPoint={focalPoint}
          isStack={Boolean(session.isStack)}
        />
        {captureInfo && <CaptureInfoPanel info={captureInfo} />}
      </div>

      <EditorInspector
        activeStep={activeStep}
        onStepChange={handleStepChange}
        parameters={parameters}
        onParameterChange={handleParameterChange}
        sliderRevert={sliderRevert}
        onSliderRevert={handleSliderRevert}
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
        stack={{
          available: Boolean(session.isStack),
          onParameterChange: (key, value) => {
            clearActivePreset();
            updateStackParameter(key, value);
          },
          onReset: () => {
            clearActivePreset();
            resetStack();
          },
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
          engines: serverConfig.starlessEngines,
          engine: parameters.starRemovalEngine,
          onEngineChange: updateStarRemovalEngine,
        }}
        denoise={{
          engines: serverConfig.denoiseEngines,
          engine: parameters.denoiseEngine,
          onEngineChange: updateDenoiseEngine,
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
          canReturnToAstroDex: Boolean(session.astrodex),
          astrodexObjectName: session.astrodex?.objectName ?? null,
          astrodexReturning: astrodex.isLoading,
          astrodexReturned: astrodex.success,
          astrodexError: astrodex.error,
          defaultFilename: defaultExportName(session),
          onDownload: (filename) => void handleDownload(filename),
          onReturnToAstroDex: () => void handleReturnToAstrodex(),
          onSaveAsPreset: () => setShowSavePreset(true),
        }}
      />

      <div className="flex flex-col gap-4 lg:sticky lg:top-20 lg:self-start">
        <ImagePreview
          originalUrl={originalUrl}
          processedUrl={processedUrl}
          histogram={session.histogram}
          aspectRatio={previewAspectRatio}
          isLoading={isProcessing}
          progress={progress}
          progressLabel={
            currentStep === 'star_removal' && parameters.starRemovalEngine === 'starnet2'
              ? t('image_preview.removing_stars_starnet2')
              : undefined
          }
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

        <MilestoneTimeline
          milestones={milestones}
          activeId={activeMilestoneId}
          onCapture={captureMilestone}
          onRestore={handleMilestoneRestore}
          disabled={isProcessing}
        />

        {showDepthViewer && (
          <div className="flex flex-col gap-2">
            {depthShift.error ? (
              <p className="rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-xs text-danger">
                {t('editor.depth_shift_failed', { error: depthShift.error })}
              </p>
            ) : depthShift.layerUrls.length === 0 ? (
              <div className="panel grid h-40 place-items-center text-xs text-faint">
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

      {confirmExit && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label={t('editor.discard_title')}
          onClick={(event) => event.target === event.currentTarget && setConfirmExit(false)}
        >
          <div className="panel flex w-full max-w-sm flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <h2 className="text-sm font-semibold text-ink">{t('editor.discard_title')}</h2>
              <p className="text-xs text-muted">{t('editor.discard_body')}</p>
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setConfirmExit(false)}
              >
                {t('common.cancel')}
              </button>
              <button
                type="button"
                className="btn btn-danger btn-sm"
                onClick={() => {
                  setConfirmExit(false);
                  onExit();
                }}
              >
                {t('editor.discard_confirm')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
