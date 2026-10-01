import { STEP_ICONS } from '@/components/EditorRail';
import { ExportPanel } from '@/components/ExportPanel';
import { FramingControls } from '@/components/FramingControls';
import { PresetButtons } from '@/components/PresetButtons';
import { SliderGroup } from '@/components/SliderGroup';
import { ToneCurveEditor } from '@/components/ToneCurveEditor';
import { ChevronIcon, SparkleIcon } from '@/components/icons';
import type { SliderRevert } from '@/hooks/useImageProcessing';
import { useTranslation } from '@/hooks/useTranslation';
import {
  DEFAULT_STACK_PARAMETERS,
  editorStepsFor,
  stackParametersEqual,
  stepIsModified,
  STRETCH_MODES,
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
  /** Auto Astro's settings are in place and untouched since - show the "done" note. */
  autoAstroApplied: boolean;
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
  /** The edited image, shown as the "ready" thumbnail. */
  resultUrl: string;
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
  /** The active slider + its pre-edit value, for the one-step revert arrow. */
  sliderRevert: SliderRevert | null;
  onSliderRevert: () => void;
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

/** Steps whose help has a longer "learn more" explanation (`editor.steps.<id>.more`). */
const STEPS_WITH_DETAILS = new Set<EditorStepId>([
  'stack',
  'sky',
  'light',
  'curves',
  'colour',
  'detail',
  'stars',
  'depth',
]);

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
    } else {
      // Only reachable with sliders: the button is hidden otherwise.
      props.onResetSection(sliderKeys);
    }
  }

  const showHeaderReset =
    sectionResettable || activeStep === 'curves' || (activeStep === 'stack' && stackModified);
  const StepIcon = STEP_ICONS[step.id];
  const NextIcon = nextStep ? STEP_ICONS[nextStep.id] : null;
  // The steps that touched the image, for the Export step's recap.
  const touchedSteps = steps
    .filter((entry) => stepIsModified(entry, parameters, props.depth.focalPoint))
    .map((entry) => t(`editor.rail.${entry.id}`));

  return (
    // z-10 lifts this column (and the parameter-hint popovers that spill out of
    // it) above the preview column, which is later in the DOM and would
    // otherwise paint over an escaping tooltip.
    <div className="panel relative z-10 flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-base font-semibold tracking-tight text-ink">
          <StepIcon className="h-5 w-5 text-accent" />
          {t(`editor.rail.${step.id}`)}
        </h2>
        {showHeaderReset && (
          <button type="button" className="btn btn-ghost btn-sm -mr-2" onClick={handleHeaderReset}>
            {t('common.reset')}
          </button>
        )}
      </div>

      <div className="-mt-2 flex flex-col gap-1">
        <p className="text-sm text-muted">{t(`editor.steps.${step.id}.help`)}</p>
        {STEPS_WITH_DETAILS.has(step.id) && (
          // Native disclosure: the long explanation stays one click away
          // instead of standing between the user and the first control.
          <details className="group text-xs text-faint">
            <summary className="flex w-fit cursor-pointer list-none items-center gap-1 font-medium text-accent outline-none hover:opacity-80 focus-visible:ring-2 focus-visible:ring-accent [&::-webkit-details-marker]:hidden">
              <ChevronIcon className="h-3 w-3 transition-transform group-open:rotate-90" />
              {t('editor.learn_more')}
            </summary>
            <p className="mt-1.5 leading-relaxed">{t(`editor.steps.${step.id}.more`)}</p>
          </details>
        )}
      </div>

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
          revert={props.sliderRevert}
          onRevert={props.onSliderRevert}
        />
      )}

      {activeStep === 'stars' && (
        <StarsPanel
          parameters={parameters}
          onParameterChange={props.onParameterChange}
          isProcessing={props.isProcessing}
          revert={props.sliderRevert}
          onRevert={props.onSliderRevert}
          stars={props.stars}
        />
      )}

      {activeStep === 'detail' && (
        <DetailPanel
          parameters={parameters}
          onParameterChange={props.onParameterChange}
          isProcessing={props.isProcessing}
          revert={props.sliderRevert}
          onRevert={props.onSliderRevert}
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
          resultUrl={props.exportActions.resultUrl}
          touchedSteps={touchedSteps}
          onDownload={props.exportActions.onDownload}
          onReturnToAstroDex={props.exportActions.onReturnToAstroDex}
          onSaveAsPreset={props.exportActions.onSaveAsPreset}
        />
      )}

      {sliderKeys.length > 0 && (
        <p className="text-[11px] text-faint">{t('editor.slider_tip')}</p>
      )}

      {NextIcon && nextStep && (
        // Workflow navigation, not a setting: set off below a hairline, on
        // the accent wash, with the next step's own icon - it must never read
        // as one more control of this step.
        <div className="-mx-4 -mb-4 mt-1 border-t border-hairline p-3 sm:-mx-5 sm:-mb-5">
          <button
            type="button"
            className="group flex w-full items-center gap-3 rounded-lg bg-accent-wash px-3 py-2.5 text-left outline-none ring-1 ring-accent/25 transition-[background-color,box-shadow] duration-150 hover:ring-accent/50 focus-visible:ring-2 focus-visible:ring-accent"
            aria-label={t('editor.next_step', { step: t(`editor.rail.${nextStep.id}`) })}
            onClick={() => onStepChange(nextStep.id)}
          >
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-surface text-accent shadow-panel">
              <NextIcon className="h-4 w-4" />
            </span>
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-accent">
                {t('editor.next_step_eyebrow')}
              </span>
              <span className="truncate text-sm font-medium text-ink">
                {t(`editor.rail.${nextStep.id}`)}
              </span>
            </span>
            <ChevronIcon className="h-4 w-4 text-accent transition-transform duration-150 group-hover:translate-x-0.5" />
          </button>
        </div>
      )}
    </div>
  );
}

function StartPanel({
  onAutoAstro,
  autoAstroLoading,
  autoAstroError,
  autoAstroApplied,
  presets,
  activePreset,
  onPresetApply,
  onPresetDelete,
  onResetAll,
  isProcessing,
}: StartBundle & { isProcessing: boolean }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <button
          type="button"
          className="btn btn-primary w-full py-2.5 text-[15px]"
          disabled={isProcessing || autoAstroLoading}
          onClick={onAutoAstro}
        >
          <SparkleIcon className={`h-5 w-5 ${autoAstroLoading ? 'animate-pulse' : ''}`} />
          {autoAstroLoading ? t('editor.auto_astro_analyzing') : t('editor.auto_astro_button')}
        </button>
        <p className="text-xs text-faint">{t('editor.auto_astro_hint')}</p>
      </div>
      {autoAstroApplied && !autoAstroError && (
        <p className="rounded-md border border-accent/30 bg-accent-wash px-3 py-2 text-xs text-ink" role="status">
          {t('editor.auto_astro_done')}
        </p>
      )}
      {autoAstroError && (
        <p className="rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-xs text-danger">
          {t('editor.auto_astro_failed', { error: autoAstroError })}
        </p>
      )}
      <div className="flex flex-col gap-2">
        <span className="flex flex-col gap-0.5">
          <span className="eyebrow">{t('editor.presets_heading')}</span>
          <span className="text-xs text-faint">{t('editor.presets_hint')}</span>
        </span>
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
        <div
          className="flex gap-1"
          role="radiogroup"
          aria-label={t('stack_panel.stretch_mode.aria')}
        >
          {STRETCH_MODES.map((mode) => (
            <button
              key={mode}
              type="button"
              role="radio"
              aria-checked={parameters.stretchMode === mode}
              disabled={isProcessing}
              className={`chip ${parameters.stretchMode === mode ? 'chip-active' : ''}`}
              onClick={() => onParameterChange('stretchMode', mode)}
            >
              {t(`stack_panel.stretch_mode.${mode}`)}
            </button>
          ))}
        </div>
        <p className="text-xs text-faint">
          {t(`stack_panel.stretch_mode.${parameters.stretchMode}_hint`)}
        </p>
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
  revert,
  onRevert,
  stars,
}: {
  parameters: ProcessingParameters;
  onParameterChange: (key: SliderParameterKey, value: number) => void;
  isProcessing: boolean;
  revert: SliderRevert | null;
  onRevert: () => void;
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
        revert={revert}
        onRevert={onRevert}
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
          revert={revert}
          onRevert={onRevert}
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
          revert={revert}
          onRevert={onRevert}
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
  revert,
  onRevert,
  denoise,
}: {
  parameters: ProcessingParameters;
  onParameterChange: (key: SliderParameterKey, value: number) => void;
  isProcessing: boolean;
  revert: SliderRevert | null;
  onRevert: () => void;
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
        revert={revert}
        onRevert={onRevert}
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
          revert={revert}
          onRevert={onRevert}
        />
      </div>
      <SliderGroup
        keys={['sharpness']}
        parameters={parameters}
        onParameterChange={onParameterChange}
        isProcessing={isProcessing}
        revert={revert}
        onRevert={onRevert}
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

