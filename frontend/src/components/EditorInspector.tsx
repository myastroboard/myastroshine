import { ExportPanel } from '@/components/ExportPanel';
import { FramingControls } from '@/components/FramingControls';
import { PresetButtons } from '@/components/PresetButtons';
import { SliderGroup } from '@/components/SliderGroup';
import { ToneCurveEditor } from '@/components/ToneCurveEditor';
import { useTranslation } from '@/hooks/useTranslation';
import {
  DEFAULT_STACK_PARAMETERS,
  editorStepsFor,
  stackParametersEqual,
  type CurveChannel,
  type CurvePoint,
  type Dimensions,
  type EditorStepId,
  type FocusPoint,
  type GeometryParameters,
  type Preset,
  type DenoiseEngine,
  type ProcessingParameters,
  type SliderParameterKey,
  type StackParameters,
  type StarlessEngine,
} from '@/types';

export interface StartBundle {
  onAutoAstro: () => void;
  autoAstroLoading: boolean;
  autoAstroError: string | null;
  presets: Preset[];
  activePreset?: string;
  onPresetApply: (id: string) => void;
  onPresetDelete: (id: string) => void;
  onResetAll: () => void;
}

export interface StackBundle {
  /** True when this session is a stacked composite (unlocks the step). */
  available: boolean;
  onParameterChange: <K extends keyof StackParameters>(key: K, value: StackParameters[K]) => void;
  onReset: () => void;
}

export interface FramingBundle {
  /** False for a stacked composite whose source dimensions aren't known. */
  available: boolean;
  dimensions: Dimensions;
  geometry: GeometryParameters;
  ratioFrac: number | null;
  dirty: boolean;
  onGeometryChange: (next: GeometryParameters) => void;
  onRatioFracChange: (next: number | null) => void;
  onApply: () => void;
  onReset: () => void;
}

export interface StarsBundle {
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
  sourceCount: number | null;
  loading: boolean;
  /** Star-removal backends the server offers (`GET /api/config`). The engine
   * picker only shows when there's more than one. */
  engines: StarlessEngine[];
  engine: StarlessEngine;
  onEngineChange: (engine: StarlessEngine) => void;
}

export interface DenoiseBundle {
  /** Denoise backends the server offers (`GET /api/config`). The engine picker
   * only shows when there's more than one. */
  engines: DenoiseEngine[];
  engine: DenoiseEngine;
  onEngineChange: (engine: DenoiseEngine) => void;
}

export interface DepthBundle {
  focalPoint: FocusPoint | null;
  picking: boolean;
  onTogglePick: () => void;
  onClear: () => void;
  onOpenViewer: () => void;
  error: string | null;
}

export interface ExportBundle {
  canReturnToAstroDex: boolean;
  astrodexObjectName: string | null;
  astrodexReturning: boolean;
  astrodexReturned: boolean;
  astrodexError: string | null;
  /** Seeds the Export step's editable filename field (no extension). */
  defaultFilename: string;
  onDownload: (filename: string) => void;
  onReturnToAstroDex: () => void;
  onSaveAsPreset: () => void;
}

export interface EditorInspectorProps {
  activeStep: EditorStepId;
  onStepChange: (step: EditorStepId) => void;
  parameters: ProcessingParameters;
  onParameterChange: (key: SliderParameterKey, value: number) => void;
  onResetSection: (keys: SliderParameterKey[]) => void;
  onCurveChange: (channel: CurveChannel, points: CurvePoint[]) => void;
  onResetCurves: () => void;
  isProcessing: boolean;
  start: StartBundle;
  stack: StackBundle;
  framing: FramingBundle;
  stars: StarsBundle;
  denoise: DenoiseBundle;
  depth: DepthBundle;
  exportActions: ExportBundle;
}

/** The single panel of controls for whichever workflow step the rail selects. */
export function EditorInspector(props: EditorInspectorProps) {
  const { t } = useTranslation();
  const { activeStep, onStepChange, parameters } = props;
  const steps = editorStepsFor(props.stack.available);
  const stepIndex = steps.findIndex((step) => step.id === activeStep);
  const step = steps[stepIndex];
  const nextStep = steps[stepIndex + 1];

  const sliderKeys = step.params;
  const sectionResettable = sliderKeys.length > 0;
  const stackModified = !stackParametersEqual(parameters.stack, DEFAULT_STACK_PARAMETERS);

  function handleHeaderReset(): void {
    if (activeStep === 'curves') {
      props.onResetCurves();
    } else if (activeStep === 'stack') {
      props.stack.onReset();
    } else if (sectionResettable) {
      props.onResetSection(sliderKeys);
    }
  }

  const showHeaderReset =
    sectionResettable || activeStep === 'curves' || (activeStep === 'stack' && stackModified);

  return (
    // z-10 lifts this column (and the parameter-hint popovers that spill out of
    // it) above the preview column, which is later in the DOM and would
    // otherwise paint over an escaping tooltip.
    <div className="panel relative z-10 flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="eyebrow">{t(`editor.rail.${step.id}`)}</h2>
        {showHeaderReset && (
          <button type="button" className="btn btn-ghost btn-sm -mr-2" onClick={handleHeaderReset}>
            {t('common.reset')}
          </button>
        )}
      </div>

      <p className="text-xs text-faint">{t(`editor.steps.${step.id}.help`)}</p>

      {activeStep === 'start' && <StartPanel {...props.start} isProcessing={props.isProcessing} />}

      {activeStep === 'stack' && (
        <StackPanel
          parameters={parameters.stack}
          onParameterChange={props.stack.onParameterChange}
          isProcessing={props.isProcessing}
        />
      )}

      {activeStep === 'frame' &&
        (props.framing.available ? (
          <FramingControls
            dimensions={props.framing.dimensions}
            geometry={props.framing.geometry}
            ratioFrac={props.framing.ratioFrac}
            dirty={props.framing.dirty}
            onGeometryChange={props.framing.onGeometryChange}
            onRatioFracChange={props.framing.onRatioFracChange}
            onApply={props.framing.onApply}
            onReset={props.framing.onReset}
            isProcessing={props.isProcessing}
          />
        ) : (
          <p className="text-xs text-faint">{t('editor.steps.frame.unavailable')}</p>
        ))}

      {sliderKeys.length > 0 && activeStep !== 'stars' && activeStep !== 'detail' && (
        <SliderGroup
          keys={sliderKeys}
          parameters={parameters}
          onParameterChange={props.onParameterChange}
          isProcessing={props.isProcessing}
        />
      )}

      {activeStep === 'stars' && (
        <StarsPanel
          parameters={parameters}
          onParameterChange={props.onParameterChange}
          isProcessing={props.isProcessing}
          stars={props.stars}
        />
      )}

      {activeStep === 'detail' && (
        <DetailPanel
          parameters={parameters}
          onParameterChange={props.onParameterChange}
          isProcessing={props.isProcessing}
          denoise={props.denoise}
        />
      )}

      {activeStep === 'curves' && (
        <ToneCurveEditor
          bare
          curves={{
            rgb: parameters.curvePoints,
            red: parameters.redCurvePoints,
            green: parameters.greenCurvePoints,
            blue: parameters.blueCurvePoints,
          }}
          onChange={props.onCurveChange}
        />
      )}

      {activeStep === 'depth' && <DepthPanel {...props.depth} isProcessing={props.isProcessing} />}

      {activeStep === 'export' && (
        <ExportPanel
          key={props.exportActions.defaultFilename}
          isProcessing={props.isProcessing}
          canReturnToAstroDex={props.exportActions.canReturnToAstroDex}
          astrodexObjectName={props.exportActions.astrodexObjectName}
          astrodexReturning={props.exportActions.astrodexReturning}
          astrodexReturned={props.exportActions.astrodexReturned}
          astrodexError={props.exportActions.astrodexError}
          defaultFilename={props.exportActions.defaultFilename}
          onDownload={props.exportActions.onDownload}
          onReturnToAstroDex={props.exportActions.onReturnToAstroDex}
          onSaveAsPreset={props.exportActions.onSaveAsPreset}
        />
      )}

      {nextStep && (
        <button
          type="button"
          className="mt-1 inline-flex items-center gap-1 self-start text-xs font-medium text-accent transition-opacity hover:opacity-80"
          onClick={() => onStepChange(nextStep.id)}
        >
          {t('editor.next_step', { step: t(`editor.rail.${nextStep.id}`) })}
          <svg viewBox="0 0 12 12" className="h-3 w-3 stroke-current" fill="none" aria-hidden>
            <path d="M4 2l4 4-4 4" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      )}
    </div>
  );
}

function StartPanel({
  onAutoAstro,
  autoAstroLoading,
  autoAstroError,
  presets,
  activePreset,
  onPresetApply,
  onPresetDelete,
  onResetAll,
  isProcessing,
}: StartBundle & { isProcessing: boolean }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-3">
      <button
        type="button"
        className="btn btn-primary btn-sm w-full"
        disabled={isProcessing || autoAstroLoading}
        onClick={onAutoAstro}
      >
        {autoAstroLoading ? t('editor.auto_astro_analyzing') : t('editor.auto_astro_button')}
      </button>
      {autoAstroError && (
        <p className="rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-xs text-danger">
          {t('editor.auto_astro_failed', { error: autoAstroError })}
        </p>
      )}
      <div className="flex flex-col gap-2">
        <span className="eyebrow">{t('editor.presets_heading')}</span>
        <PresetButtons
          presets={presets}
          activePreset={activePreset}
          onPresetApply={onPresetApply}
          onPresetDelete={onPresetDelete}
        />
      </div>
      <button
        type="button"
        className="btn btn-ghost btn-sm self-start"
        disabled={isProcessing}
        onClick={onResetAll}
      >
        {t('editor.reset_all')}
      </button>
    </div>
  );
}

/**
 * The Stack step (composite sessions only): the linear post-stack pre-stage.
 * It runs on the 32-bit stacked composite ahead of every other stage - stretch
 * the faint signal, subtract the sky gradient, neutralise the colour - all
 * non-destructive, recomputed from the linear composite on every change.
 */
function StackPanel({
  parameters,
  onParameterChange,
  isProcessing,
}: {
  parameters: StackParameters;
  onParameterChange: <K extends keyof StackParameters>(key: K, value: StackParameters[K]) => void;
  isProcessing: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5 text-sm">
        <span className="flex items-baseline justify-between">
          <label htmlFor="stack-stretch" className="text-muted">
            {t('stack_panel.stretch.label')}
          </label>
          <span className="text-xs tabular-nums text-faint">
            {Math.round(parameters.stretch * 100)}
          </span>
        </span>
        <input
          id="stack-stretch"
          type="range"
          className="slider"
          min={0}
          max={1}
          step={0.01}
          value={parameters.stretch}
          disabled={isProcessing}
          onChange={(event) => onParameterChange('stretch', Number(event.target.value))}
        />
        <p className="text-xs text-faint">{t('stack_panel.stretch.hint')}</p>
      </div>

      <div className="flex flex-col gap-1.5 text-sm">
        <span className="flex items-baseline justify-between">
          <label htmlFor="stack-bg" className="text-muted">
            {t('stack_panel.background_extraction.label')}
          </label>
          <span className="text-xs tabular-nums text-faint">
            {parameters.backgroundExtraction}
          </span>
        </span>
        <input
          id="stack-bg"
          type="range"
          className="slider"
          min={0}
          max={100}
          step={1}
          value={parameters.backgroundExtraction}
          disabled={isProcessing}
          onChange={(event) =>
            onParameterChange('backgroundExtraction', Number(event.target.value))
          }
        />
        <p className="text-xs text-faint">{t('stack_panel.background_extraction.hint')}</p>
      </div>

      <label className="flex items-center justify-between gap-2 text-sm text-muted">
        <span className="flex flex-col gap-0.5">
          {t('stack_panel.color_calibration.label')}
          <span className="text-xs text-faint">{t('stack_panel.color_calibration.hint')}</span>
        </span>
        <input
          type="checkbox"
          className="size-4 shrink-0 accent-accent"
          checked={parameters.colorCalibration}
          disabled={isProcessing}
          onChange={(event) => onParameterChange('colorCalibration', event.target.checked)}
        />
      </label>
    </div>
  );
}

/**
 * The Stars step: two ways to handle stars, grouped so it's clear which is
 * which and when to reach for it. "Reduce" shrinks each star where it is (quick,
 * every star kept). "Remove" lifts the stars out entirely so every other step
 * only touches the nebula, then fades them back in (the starless workflow).
 * Both read the same "Detection" controls.
 */
function StarsPanel({
  parameters,
  onParameterChange,
  isProcessing,
  stars,
}: {
  parameters: ProcessingParameters;
  onParameterChange: (key: SliderParameterKey, value: number) => void;
  isProcessing: boolean;
  stars: StarsBundle;
}) {
  const { t } = useTranslation();
  const sub = (keys: SliderParameterKey[], id: string) => (
    <div className="flex flex-col gap-2">
      <span className="text-xs font-medium text-ink">{t(`stars_panel.${id}.heading`)}</span>
      <p className="text-xs text-faint">{t(`stars_panel.${id}.help`)}</p>
      <SliderGroup
        keys={keys}
        parameters={parameters}
        onParameterChange={onParameterChange}
        isProcessing={isProcessing}
      />
    </div>
  );
  return (
    <div className="flex flex-col gap-4">
      {sub(['starReduction'], 'reduce')}
      <div className="flex flex-col gap-2">
        <span className="text-xs font-medium text-ink">{t('stars_panel.remove.heading')}</span>
        <p className="text-xs text-faint">{t('stars_panel.remove.help')}</p>
        {stars.engines.length > 1 && (
          <EnginePicker
            engines={stars.engines}
            engine={stars.engine}
            onChange={stars.onEngineChange}
            disabled={isProcessing}
            i18nPrefix="stars_panel.remove.engine"
            hintEngine="starnet2"
          />
        )}
        <SliderGroup
          keys={['starRemoval', 'starRecombine']}
          parameters={parameters}
          onParameterChange={onParameterChange}
          isProcessing={isProcessing}
        />
      </div>
      <div className="flex flex-col gap-2">
        <span className="text-xs font-medium text-ink">
          {t('stars_panel.detection.heading')}
        </span>
        <p className="text-xs text-faint">{t('stars_panel.detection.help')}</p>
        <SliderGroup
          keys={['starSensitivity', 'starMaxSize']}
          parameters={parameters}
          onParameterChange={onParameterChange}
          isProcessing={isProcessing}
        />
        <StarMaskToggle {...stars} />
      </div>
    </div>
  );
}

/** Pick an ML backend for a stage. Only rendered when the server offers more than
 * one (i.e. the operator has a working binary - see docs/ALGORITHMS.md "Quality
 * path"). ``i18nPrefix`` keys the aria-label (``.aria``), each engine's chip label
 * (``.<engine>``), and the optional active-engine ``hint``. */
function EnginePicker<E extends string>({
  engines,
  engine,
  onChange,
  disabled,
  i18nPrefix,
  hintEngine,
}: {
  engines: E[];
  engine: E;
  onChange: (engine: E) => void;
  disabled: boolean;
  i18nPrefix: string;
  hintEngine?: E;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-1">
      <div className="flex gap-1" role="radiogroup" aria-label={t(`${i18nPrefix}.aria`)}>
        {engines.map((entry) => (
          <button
            key={entry}
            type="button"
            role="radio"
            aria-checked={engine === entry}
            disabled={disabled}
            className={`chip ${engine === entry ? 'chip-active' : ''}`}
            onClick={() => onChange(entry)}
          >
            {t(`${i18nPrefix}.${entry}`)}
          </button>
        ))}
      </div>
      {hintEngine && engine === hintEngine && (
        <p className="text-xs text-faint">{t(`${i18nPrefix}.hint`)}</p>
      )}
    </div>
  );
}

function DetailPanel({
  parameters,
  onParameterChange,
  isProcessing,
  denoise,
}: {
  parameters: ProcessingParameters;
  onParameterChange: (key: SliderParameterKey, value: number) => void;
  isProcessing: boolean;
  denoise: DenoiseBundle;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-4">
      <SliderGroup
        keys={['clarity']}
        parameters={parameters}
        onParameterChange={onParameterChange}
        isProcessing={isProcessing}
      />
      <div className="flex flex-col gap-2">
        <span className="text-xs font-medium text-ink">{t('detail_panel.denoise.heading')}</span>
        {denoise.engines.length > 1 && (
          <EnginePicker
            engines={denoise.engines}
            engine={denoise.engine}
            onChange={denoise.onEngineChange}
            disabled={isProcessing}
            i18nPrefix="detail_panel.denoise.engine"
            hintEngine="deepsnr"
          />
        )}
        <SliderGroup
          keys={['denoise', 'chromaDenoise']}
          parameters={parameters}
          onParameterChange={onParameterChange}
          isProcessing={isProcessing}
        />
      </div>
      <SliderGroup
        keys={['sharpness']}
        parameters={parameters}
        onParameterChange={onParameterChange}
        isProcessing={isProcessing}
      />
    </div>
  );
}

function StarMaskToggle({ enabled, onToggle, sourceCount, loading }: StarsBundle) {
  const { t } = useTranslation();
  return (
    <label className="flex items-center justify-between gap-2 text-sm text-muted">
      <span className="inline-flex items-center gap-1.5">
        {t('slider_panel.show_star_mask')}
        {enabled && (
          <span className="text-xs tabular-nums text-faint">
            {loading
              ? '...'
              : sourceCount !== null
                ? t('slider_panel.sources_count', { count: sourceCount })
                : ''}
          </span>
        )}
      </span>
      <input
        type="checkbox"
        className="size-4 accent-accent"
        checked={enabled}
        onChange={(event) => onToggle(event.target.checked)}
      />
    </label>
  );
}

function DepthPanel({
  focalPoint,
  picking,
  onTogglePick,
  onClear,
  onOpenViewer,
  error,
  isProcessing,
}: DepthBundle & { isProcessing: boolean }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className={`btn btn-sm ${picking ? 'btn-primary' : 'btn-outline'}`}
          onClick={onTogglePick}
        >
          {picking
            ? t('common.cancel')
            : focalPoint
              ? t('image_preview.change_focal_point')
              : t('image_preview.set_focal_point')}
        </button>
        {focalPoint && !picking && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClear}>
            {t('image_preview.clear_focal_point')}
          </button>
        )}
      </div>
      <button
        type="button"
        className="btn btn-outline btn-sm self-start"
        disabled={isProcessing}
        onClick={onOpenViewer}
      >
        {t('image_preview.open_depth_shift')}
      </button>
      {error && (
        <p className="rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-xs text-danger">
          {t('editor.depth_shift_failed', { error })}
        </p>
      )}
    </div>
  );
}

