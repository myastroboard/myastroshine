import type { ReactNode } from 'react';

import { STEP_ICONS } from '@/components/EditorRail';
import { ExportPanel } from '@/components/ExportPanel';
import { FramingControls } from '@/components/FramingControls';
import { PresetButtons } from '@/components/PresetButtons';
import { SliderGroup } from '@/components/SliderGroup';
import { StylePanel } from '@/components/StylePanel';
import { ToneCurveEditor } from '@/components/ToneCurveEditor';
import { ChevronIcon, SparkleIcon } from '@/components/icons';
import type { SliderRevert } from '@/hooks/useImageProcessing';
import { useTranslation } from '@/hooks/useTranslation';
import {
  DEFAULT_STACK_PARAMETERS,
  editorStepsFor,
  stackParametersEqual,
  starsSeparated,
  stepIsModified,
  STRETCH_MODES,
  type CurveChannel,
  type CurvePoint,
  type Dimensions,
  type EditorStepId,
  type FocusPoint,
  type GeometryParameters,
  type LookCatalog,
  type LookId,
  type LookParameters,
  type LookScene,
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

export interface StyleBundle {
  /** The looks this session's gallery offers (night-landscape ones first). */
  catalog: LookCatalog;
  /** The gallery group of the built-in preset last applied, if any. */
  suggestedScene: LookScene | null;
  /** Gallery thumbnail URL for a look (`null`: the edit without a look). */
  thumbnailUrl: (look: LookId | null) => string;
  onLookChange: <K extends keyof LookParameters>(key: K, value: LookParameters[K]) => void;
  onReset: () => void;
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
  onDownload: (filename: string, withStyle: boolean) => void;
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
  style: StyleBundle;
  exportActions: ExportBundle;
}

/** Steps whose help has a longer "learn more" explanation (`editor.steps.<id>.more`). */
const STEPS_WITH_DETAILS = new Set<EditorStepId>([
  'stack',
  'sky',
  'noise',
  'starless',
  'light',
  'curves',
  'colour',
  'detail',
  'stars',
  'depth',
  'style',
]);

/** Steps whose sliders come in titled groups (their own panel below), not as
 * one flat list. */
const GROUPED_SLIDER_STEPS = new Set<EditorStepId>(['sky', 'noise', 'starless', 'stars']);

/** The single panel of controls for whichever workflow step the rail selects. */
export function EditorInspector(props: EditorInspectorProps) {
  const { t } = useTranslation();
  const { activeStep, onStepChange, parameters } = props;
  const steps = editorStepsFor(props.stack.available);
  const stepIndex = steps.findIndex((step) => step.id === activeStep);
  const step = steps[stepIndex];
  const nextStep = steps[stepIndex + 1];

  const sliderKeys = step.params;
  const sliderProps: SliderPanelProps = {
    parameters,
    onParameterChange: props.onParameterChange,
    isProcessing: props.isProcessing,
    revert: props.sliderRevert,
    onRevert: props.onSliderRevert,
  };
  const sectionResettable = sliderKeys.length > 0;
  const stackModified = !stackParametersEqual(parameters.stack, DEFAULT_STACK_PARAMETERS);

  function handleHeaderReset(): void {
    if (activeStep === 'curves') {
      props.onResetCurves();
    } else if (activeStep === 'stack') {
      props.stack.onReset();
    } else if (activeStep === 'style') {
      props.style.onReset();
    } else {
      // Only reachable with sliders: the button is hidden otherwise.
      props.onResetSection(sliderKeys);
    }
  }

  const showHeaderReset =
    sectionResettable ||
    activeStep === 'curves' ||
    (activeStep === 'stack' && stackModified) ||
    (activeStep === 'style' && parameters.look.lookId !== null);
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

      {step.phase === 'enhance' && starsSeparated(parameters) && (
        // The starless bracket, said where it applies: these steps edit the sky
        // alone, and the stars are still waiting in the Stars step.
        <div
          className="flex flex-col items-start gap-1.5 rounded-md border border-accent/30 bg-accent-wash px-3 py-2 text-xs text-ink"
          role="note"
        >
          <p>{t('editor.starless_banner')}</p>
          <button
            type="button"
            className="font-medium text-accent hover:opacity-80"
            onClick={() => onStepChange('stars')}
          >
            {t('editor.starless_banner_action')}
          </button>
        </div>
      )}

      {activeStep === 'export' && starsSeparated(parameters) && parameters.starRecombine === 0 && (
        // Separated and never put back: almost always a forgotten step.
        <div
          className="flex flex-col items-start gap-1.5 rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-xs text-danger"
          role="status"
        >
          <p>{t('editor.stars_not_back')}</p>
          <button
            type="button"
            className="font-medium underline hover:opacity-80"
            onClick={() => onStepChange('stars')}
          >
            {t('editor.starless_banner_action')}
          </button>
        </div>
      )}

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

      {sliderKeys.length > 0 && !GROUPED_SLIDER_STEPS.has(activeStep) && (
        <SliderGroup keys={sliderKeys} {...sliderProps} />
      )}

      {activeStep === 'sky' && <SkyPanel {...sliderProps} />}

      {activeStep === 'noise' && <NoisePanel {...sliderProps} denoise={props.denoise} />}

      {activeStep === 'starless' && <StarlessPanel {...sliderProps} stars={props.stars} />}

      {activeStep === 'stars' && (
        <StarsPanel {...sliderProps} onGoToStarless={() => onStepChange('starless')} />
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

      {activeStep === 'style' && (
        <StylePanel
          look={parameters.look}
          catalog={props.style.catalog}
          suggestedScene={props.style.suggestedScene}
          thumbnailUrl={props.style.thumbnailUrl}
          onLookChange={props.style.onLookChange}
          isProcessing={props.isProcessing}
        />
      )}

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
          styleName={
            parameters.look.lookId === null
              ? null
              : t(`style_panel.looks.${parameters.look.lookId}.name`)
          }
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

/** What every slider panel below passes straight through to its `SliderGroup`s. */
interface SliderPanelProps {
  parameters: ProcessingParameters;
  onParameterChange: (key: SliderParameterKey, value: number) => void;
  isProcessing: boolean;
  revert: SliderRevert | null;
  onRevert: () => void;
}

/** A titled group of sliders inside a step: heading, one line of help, the
 * sliders, then whatever extra control the group needs (`children`). */
function SliderSection({
  id,
  keys,
  children,
  ...sliders
}: SliderPanelProps & { id: string; keys: SliderParameterKey[]; children?: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-2">
      <span className="text-xs font-medium text-ink">{t(`${id}.heading`)}</span>
      <p className="text-xs text-faint">{t(`${id}.help`)}</p>
      {children}
      <SliderGroup keys={keys} {...sliders} />
    </div>
  );
}

/**
 * The sky step, in the order the corrections run: the background first
 * (vignette, light-pollution gradient, haze), then the colour balance read on
 * that flattened background, the green cast last.
 */
function SkyPanel(props: SliderPanelProps) {
  return (
    <div className="flex flex-col gap-4">
      <SliderSection
        id="sky_panel.background"
        keys={['vignetteCorrection', 'gradientReduction', 'dehaze']}
        {...props}
      />
      <SliderSection id="sky_panel.colour" keys={['temperature', 'tint', 'greenRemoval']} {...props} />
    </div>
  );
}

/** The noise step: before the stars are separated and before any tone push. */
function NoisePanel({ denoise, ...props }: SliderPanelProps & { denoise: DenoiseBundle }) {
  return (
    <SliderSection id="noise_panel" keys={['denoise', 'chromaDenoise']} {...props}>
      {denoise.engines.length > 1 && (
        <EnginePicker
          engines={denoise.engines}
          engine={denoise.engine}
          onChange={denoise.onEngineChange}
          disabled={props.isProcessing}
          i18nPrefix="noise_panel.engine"
          hintEngine="deepsnr"
        />
      )}
    </SliderSection>
  );
}

/**
 * "Separate stars": the first half of the starless workflow. Which points count
 * as stars (shared with the Stars step's in-place shrink), then how much of them
 * to lift out of the sky - the Enhance steps then work on the sky alone, and the
 * Stars step puts them back.
 */
function StarlessPanel({ stars, ...props }: SliderPanelProps & { stars: StarsBundle }) {
  return (
    <div className="flex flex-col gap-4">
      <SliderSection id="stars_panel.detection" keys={['starSensitivity', 'starMaxSize']} {...props}>
        <StarMaskToggle {...stars} />
      </SliderSection>
      <SliderSection id="stars_panel.remove" keys={['starRemoval']} {...props}>
        {stars.engines.length > 1 && (
          <EnginePicker
            engines={stars.engines}
            engine={stars.engine}
            onChange={stars.onEngineChange}
            disabled={props.isProcessing}
            i18nPrefix="stars_panel.remove.engine"
            hintEngine="starnet2"
          />
        )}
      </SliderSection>
    </div>
  );
}

/**
 * "Stars": the second half, after the sky work. With the stars separated,
 * shrink the stars layer and put it back over the edited sky. Without, there is
 * nothing to put back: the stars are shrunk where they are, found by the
 * detection set in "Separate stars".
 */
function StarsPanel({
  onGoToStarless,
  ...props
}: SliderPanelProps & { onGoToStarless: () => void }) {
  const { t } = useTranslation();
  const separated = starsSeparated(props.parameters);
  return (
    <div className="flex flex-col gap-4">
      {separated ? (
        <SliderSection id="stars_panel.back" keys={['starRecombine']} {...props} />
      ) : (
        <p className="text-xs text-faint">{t('stars_panel.not_separated')}</p>
      )}
      <SliderSection
        id={separated ? 'stars_panel.reduce_layer' : 'stars_panel.reduce'}
        keys={['starReduction']}
        {...props}
      />
      {!separated && (
        <button type="button" className="btn btn-ghost btn-sm self-start" onClick={onGoToStarless}>
          {t('stars_panel.detection_link')}
        </button>
      )}
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

