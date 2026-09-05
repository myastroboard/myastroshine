import { ExportPanel } from '@/components/ExportPanel';
import { FramingControls } from '@/components/FramingControls';
import { PresetButtons } from '@/components/PresetButtons';
import { SliderGroup } from '@/components/SliderGroup';
import { ToneCurveEditor } from '@/components/ToneCurveEditor';
import { useTranslation } from '@/hooks/useTranslation';
import {
  EDITOR_STEPS,
  type CurveChannel,
  type CurvePoint,
  type Dimensions,
  type EditorStepId,
  type FocusPoint,
  type GeometryParameters,
  type Preset,
  type ProcessingParameters,
  type SliderParameterKey,
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
  canSendToAstroDex: boolean;
  onDownload: () => void;
  onSendToAstroDex: () => void;
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
  framing: FramingBundle;
  stars: StarsBundle;
  depth: DepthBundle;
  exportActions: ExportBundle;
}

/** The single panel of controls for whichever workflow step the rail selects. */
export function EditorInspector(props: EditorInspectorProps) {
  const { t } = useTranslation();
  const { activeStep, onStepChange, parameters } = props;
  const stepIndex = EDITOR_STEPS.findIndex((step) => step.id === activeStep);
  const step = EDITOR_STEPS[stepIndex];
  const nextStep = EDITOR_STEPS[stepIndex + 1];

  const sliderKeys = step.params;
  const sectionResettable = sliderKeys.length > 0;

  function handleHeaderReset(): void {
    if (activeStep === 'curves') {
      props.onResetCurves();
    } else if (sectionResettable) {
      props.onResetSection(sliderKeys);
    }
  }

  const showHeaderReset = sectionResettable || activeStep === 'curves';

  return (
    <div className="panel flex flex-col gap-4">
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

      {sliderKeys.length > 0 && (
        <SliderGroup
          keys={sliderKeys}
          parameters={parameters}
          onParameterChange={props.onParameterChange}
          isProcessing={props.isProcessing}
        />
      )}

      {activeStep === 'stars' && (
        <StarMaskToggle {...props.stars} />
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
          isProcessing={props.isProcessing}
          canSendToAstroDex={props.exportActions.canSendToAstroDex}
          onDownload={props.exportActions.onDownload}
          onSendToAstroDex={props.exportActions.onSendToAstroDex}
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

