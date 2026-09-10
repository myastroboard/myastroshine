// Shared type definitions for the MyAstroShine frontend.
// Keep in sync with backend/app/models and docs/API.md.

export interface Dimensions {
  width: number;
  height: number;
}

export interface HistogramData {
  r: number[];
  g: number[];
  b: number[];
}

/** Framing applied before enhancement. Edited in the crop tool, not by sliders. */
export interface GeometryParameters {
  straighten: number; // degrees, -45..45
  rotateQuarters: number; // 0..3, clockwise 90deg turns
  flipHorizontal: boolean;
  flipVertical: boolean;
  cropX: number; // 0..1 fractions of the rotated/flipped image
  cropY: number;
  cropW: number;
  cropH: number;
}

export const DEFAULT_GEOMETRY: GeometryParameters = {
  straighten: 0,
  rotateQuarters: 0,
  flipHorizontal: false,
  flipVertical: false,
  cropX: 0,
  cropY: 0,
  cropW: 1,
  cropH: 1,
};

export function isDefaultGeometry(geometry: GeometryParameters): boolean {
  return (
    geometry.straighten === 0 &&
    geometry.rotateQuarters === 0 &&
    !geometry.flipHorizontal &&
    !geometry.flipVertical &&
    geometry.cropX === 0 &&
    geometry.cropY === 0 &&
    geometry.cropW === 1 &&
    geometry.cropH === 1
  );
}

export function geometryEquals(a: GeometryParameters, b: GeometryParameters): boolean {
  return (
    a.straighten === b.straighten &&
    a.rotateQuarters === b.rotateQuarters &&
    a.flipHorizontal === b.flipHorizontal &&
    a.flipVertical === b.flipVertical &&
    a.cropX === b.cropX &&
    a.cropY === b.cropY &&
    a.cropW === b.cropW &&
    a.cropH === b.cropH
  );
}

/** One control point of the tone curve: 8-bit input/output level, both 0-255. */
export interface CurvePoint {
  x: number;
  y: number;
}

/** The default (and only always-present) curve: a straight identity line. */
export const DEFAULT_CURVE_POINTS: CurvePoint[] = [
  { x: 0, y: 0 },
  { x: 255, y: 255 },
];

/**
 * Linear post-stack controls, shown only for a stacked-composite session (the
 * "Stack" step). They run as a non-destructive pre-stage on the 32-bit linear
 * composite, ahead of every other stage. Ignored for an ordinary image.
 */
export interface StackParameters {
  /** Auto-stretch intensity: 0 = subtle (dark sky), 1 = aggressive. */
  stretch: number;
  /** How much of the fitted low-order sky gradient to remove (0 = off, 100 = full). */
  backgroundExtraction: number;
  /** Neutralise the sky background and balance the channels toward grey. */
  colorCalibration: boolean;
}

export const DEFAULT_STACK_PARAMETERS: StackParameters = {
  stretch: 0.5,
  backgroundExtraction: 100,
  colorCalibration: true,
};

export function stackParametersEqual(a: StackParameters, b: StackParameters): boolean {
  return (
    a.stretch === b.stretch &&
    a.backgroundExtraction === b.backgroundExtraction &&
    a.colorCalibration === b.colorCalibration
  );
}

export interface ProcessingParameters {
  geometry: GeometryParameters;
  stack: StackParameters;
  contrast: number;
  exposure: number;
  saturation: number;
  highlights: number;
  shadows: number;
  whites: number;
  blacks: number;
  clarity: number;
  vibrance: number;
  denoise: number;
  /** Backend for the `denoise` stage. `'deepsnr'` is honoured only when the
   * operator has a working binary; otherwise the classical filter runs. Ignored
   * when `denoise === 0`; `chromaDenoise` is always classical. */
  denoiseEngine: DenoiseEngine;
  chromaDenoise: number;
  vignetteCorrection: number;
  gradientReduction: number;
  dehaze: number;
  starReduction: number;
  starSensitivity: number;
  starMaxSize: number;
  starRemoval: number;
  starRecombine: number;
  /** Which backend performs the star/nebula split. `'starnet2'` is honoured only
   * when the operator has a working binary; the pipeline otherwise uses the
   * classical split. Ignored when `starRemoval === 0`. */
  starRemovalEngine: StarlessEngine;
  sharpness: number;
  temperature: number;
  tint: number;
  curvePoints: CurvePoint[];
  redCurvePoints: CurvePoint[];
  greenCurvePoints: CurvePoint[];
  blueCurvePoints: CurvePoint[];
}

export const DEFAULT_PARAMETERS: ProcessingParameters = {
  geometry: DEFAULT_GEOMETRY,
  stack: DEFAULT_STACK_PARAMETERS,
  contrast: 1.0,
  exposure: 0.0,
  saturation: 1.0,
  highlights: 0.0,
  shadows: 0.0,
  whites: 0.0,
  blacks: 0.0,
  clarity: 0.0,
  vibrance: 1.0,
  denoise: 0,
  denoiseEngine: 'classic',
  chromaDenoise: 0,
  vignetteCorrection: 0,
  gradientReduction: 0,
  dehaze: 0,
  starReduction: 0,
  starSensitivity: 50,
  starMaxSize: 30,
  starRemoval: 0,
  starRecombine: 0,
  starRemovalEngine: 'classic',
  sharpness: 1.0,
  temperature: 6500,
  tint: 0,
  curvePoints: [], // empty = no curve (identity); the editor shows DEFAULT_CURVE_POINTS instead
  redCurvePoints: [],
  greenCurvePoints: [],
  blueCurvePoints: [],
};

/** True once any parameter, the framing, or a tone curve has left its default -
 * i.e. there is edit work that would be lost by leaving the editor. */
export function hasEdits(p: ProcessingParameters): boolean {
  if (!isDefaultGeometry(p.geometry)) {
    return true;
  }
  if (!stackParametersEqual(p.stack, DEFAULT_STACK_PARAMETERS)) {
    return true;
  }
  for (const key of Object.keys(DEFAULT_PARAMETERS) as (keyof ProcessingParameters)[]) {
    if (key === 'geometry' || key === 'stack') {
      continue;
    }
    const value = p[key];
    if (Array.isArray(value)) {
      if (value.length > 0) {
        return true;
      }
    } else if (value !== DEFAULT_PARAMETERS[key]) {
      return true;
    }
  }
  return false;
}

/** Deep value-equality for two curves (their control-point lists). */
function curvePointsEqual(a: CurvePoint[], b: CurvePoint[]): boolean {
  return a.length === b.length && a.every((p, i) => p.x === b[i].x && p.y === b[i].y);
}

/** True when two parameter sets would produce the same processed image - every
 * scalar, the framing, and all four tone curves match. Mirrors the key walk in
 * {@link hasEdits}. */
export function parametersEqual(a: ProcessingParameters, b: ProcessingParameters): boolean {
  if (!geometryEquals(a.geometry, b.geometry)) {
    return false;
  }
  if (!stackParametersEqual(a.stack, b.stack)) {
    return false;
  }
  for (const key of Object.keys(DEFAULT_PARAMETERS) as (keyof ProcessingParameters)[]) {
    if (key === 'geometry' || key === 'stack') {
      continue;
    }
    const av = a[key];
    const bv = b[key];
    if (Array.isArray(av) || Array.isArray(bv)) {
      if (!Array.isArray(av) || !Array.isArray(bv) || !curvePointsEqual(av, bv)) {
        return false;
      }
    } else if (av !== bv) {
      return false;
    }
  }
  return true;
}

/** Curve fields, keyed by the channel the ToneCurveEditor tab selector edits. */
export const CURVE_CHANNELS = ['rgb', 'red', 'green', 'blue'] as const;
export type CurveChannel = (typeof CURVE_CHANNELS)[number];

export const CURVE_CHANNEL_FIELD: Record<CurveChannel, keyof ProcessingParameters> = {
  rgb: 'curvePoints',
  red: 'redCurvePoints',
  green: 'greenCurvePoints',
  blue: 'blueCurvePoints',
};

/** Numeric parameters driven by the slider panel (everything but geometry / stack /
 * curve fields, and the discrete engine choices, which are pickers, not sliders). */
export type SliderParameterKey = Exclude<
  keyof ProcessingParameters,
  | 'geometry'
  | 'stack'
  | 'curvePoints'
  | 'redCurvePoints'
  | 'greenCurvePoints'
  | 'blueCurvePoints'
  | 'starRemovalEngine'
  | 'denoiseEngine'
>;

interface ParameterBound {
  key: SliderParameterKey;
  min: number;
  max: number;
  step: number;
}

/**
 * Slider min/max/step per parameter. Which panel a slider appears in, and in
 * what order, is decided by {@link EDITOR_STEPS} - not here. Label and hint text
 * live in the i18n files, keyed by `key` (`slider_panel.params.<key>.label` /
 * `.hint`) - see `SliderGroup.tsx`. Consumers use {@link PARAMETER_BOUND_BY_KEY}.
 */
const PARAMETER_BOUNDS: ParameterBound[] = [
  { key: 'contrast', min: 0.5, max: 3.0, step: 0.01 },
  { key: 'exposure', min: -1.0, max: 1.0, step: 0.01 },
  { key: 'highlights', min: -1.0, max: 1.0, step: 0.01 },
  { key: 'shadows', min: -1.0, max: 1.0, step: 0.01 },
  { key: 'whites', min: -1.0, max: 1.0, step: 0.01 },
  { key: 'blacks', min: -1.0, max: 1.0, step: 0.01 },
  { key: 'vignetteCorrection', min: 0, max: 100, step: 1 },
  { key: 'gradientReduction', min: 0, max: 100, step: 1 },
  { key: 'dehaze', min: 0, max: 100, step: 1 },
  { key: 'clarity', min: -1.0, max: 1.0, step: 0.01 },
  { key: 'denoise', min: 0, max: 100, step: 1 },
  { key: 'chromaDenoise', min: 0, max: 100, step: 1 },
  { key: 'starReduction', min: 0, max: 100, step: 1 },
  { key: 'starSensitivity', min: 0, max: 100, step: 1 },
  { key: 'starMaxSize', min: 0, max: 100, step: 1 },
  { key: 'starRemoval', min: 0, max: 100, step: 1 },
  { key: 'starRecombine', min: 0, max: 100, step: 1 },
  { key: 'sharpness', min: 0.0, max: 2.0, step: 0.01 },
  { key: 'vibrance', min: 0.0, max: 2.0, step: 0.01 },
  { key: 'saturation', min: 0.0, max: 2.0, step: 0.01 },
  { key: 'temperature', min: 2000, max: 8000, step: 50 },
  { key: 'tint', min: -50, max: 50, step: 1 },
];

export const PARAMETER_BOUND_BY_KEY: Partial<Record<SliderParameterKey, ParameterBound>> =
  Object.fromEntries(PARAMETER_BOUNDS.map((bound) => [bound.key, bound]));

/**
 * The editor workflow, in retouching order. This mirrors the backend pipeline
 * order in `app/services/image_processing.py::apply_parameters`: geometry first,
 * then white balance and background corrections, then tone, curves, colour,
 * detail, then stars (reduce in place, or remove entirely - `star_removal`
 * splits the backend pipeline; see that method). The rail, the inspector panel
 * switch, and the "modified" dots all derive from this one list.
 *
 * `start` and `export` are workflow brackets (no step number): a one-click
 * starting point, and getting the result out.
 */
export type EditorStepId =
  | 'start'
  | 'stack'
  | 'frame'
  | 'sky'
  | 'light'
  | 'curves'
  | 'colour'
  | 'detail'
  | 'stars'
  | 'depth'
  | 'export';

export interface EditorStep {
  id: EditorStepId;
  /** Position in the workflow (1-8), or null for the start/stack/export brackets. */
  number: number | null;
  /** Slider parameters shown in this step's panel, in display order. */
  params: SliderParameterKey[];
  /** Only shown for a stacked-composite session. */
  stackOnly?: boolean;
}

export const EDITOR_STEPS: EditorStep[] = [
  { id: 'start', number: null, params: [] },
  { id: 'stack', number: null, params: [], stackOnly: true },
  { id: 'frame', number: 1, params: [] },
  {
    id: 'sky',
    number: 2,
    params: ['temperature', 'tint', 'vignetteCorrection', 'gradientReduction', 'dehaze'],
  },
  {
    id: 'light',
    number: 3,
    params: ['exposure', 'contrast', 'highlights', 'shadows', 'whites', 'blacks'],
  },
  { id: 'curves', number: 4, params: [] },
  { id: 'colour', number: 5, params: ['saturation', 'vibrance'] },
  { id: 'detail', number: 6, params: ['clarity', 'denoise', 'chromaDenoise', 'sharpness'] },
  {
    id: 'stars',
    number: 7,
    // Reduce (shrink in place), remove (starless split + recombine), and the
    // shared detection controls - all rendered as one grouped panel, see
    // EditorInspector's StarsPanel.
    params: ['starReduction', 'starRemoval', 'starRecombine', 'starSensitivity', 'starMaxSize'],
  },
  { id: 'depth', number: 8, params: [] },
  { id: 'export', number: null, params: [] },
];

/** The workflow steps visible for this session - the "Stack" step only for a composite. */
export function editorStepsFor(isStack: boolean): EditorStep[] {
  return isStack ? EDITOR_STEPS : EDITOR_STEPS.filter((step) => !step.stackOnly);
}

export interface UploadResponse {
  sessionId: string;
  imageUrl: string;
  dimensions: Dimensions;
  fileSizeBytes: number;
  histogram: HistogramData;
  uploadTimestamp: string;
  expiresAt: string;
  /** The upload was linear stack data (FITS / 16-bit export) and opened as a
   * composite session - the editor shows the linear "Stack" step. */
  isStack: boolean;
}

export interface ProcessResponse {
  sessionId: string;
  jobId: string;
  status: string;
  previewUrl: string;
  estimatedTimeSeconds: number;
  wsStatusUrl: string;
}

/** Same shape as {@link ProcessResponse} plus the computed parameters. */
export interface AutoAstroResult extends ProcessResponse {
  parameters: ProcessingParameters;
}

/**
 * Minimal handle the editor needs. A fresh upload provides the full
 * {@link UploadResponse}; a stacked composite only carries its session id.
 */
export interface EditorSession {
  sessionId: string;
  histogram?: HistogramData;
  dimensions?: Dimensions;
  /** Name of the uploaded file, when the session started from an upload - seeds
   * the Export step's filename field. Absent for stacks and AstroDex handoffs. */
  originalFilename?: string;
  /** True when the session is a stacked composite - unlocks the "Stack" step. */
  isStack?: boolean;
  /** Set when the session was opened from an AstroDex handoff - unlocks the
   * "Send back to AstroDex" action in the Export step. */
  astrodex?: AstroDexReturn;
}

/** What the editor needs to send the enhanced result back to AstroDex. */
export interface AstroDexReturn {
  itemId: string;
  objectName: string | null;
}

export interface HandoffResumeResponse {
  sessionId: string;
  imageUrl: string;
  dimensions: Dimensions;
  histogram: HistogramData;
  objectName: string | null;
  astrodexItemId: string;
}

export interface HandoffReturnResponse {
  sessionId: string;
  status: 'received' | 'pending' | 'sent' | 'failed';
  astrodexItemId: string;
}

export type JobStatus = 'queued' | 'processing' | 'completed' | 'failed' | 'superseded';

export interface ProcessingStatus {
  jobId: string;
  status: JobStatus;
  progressPercent: number;
  currentStep: string;
  /** Short language-neutral detail for the current step, e.g. "340/1066" (stacking). */
  detail?: string;
  message: string;
  error?: string;
}

export interface Preset {
  presetId: string;
  name: string;
  category: string;
  description: string;
  parameters: ProcessingParameters;
  author: string;
  isFavorite: boolean;
  createdAt?: string;
}

// --- Webhook tokens ------------------------------------------------------

export interface WebhookToken {
  id: string;
  name: string;
  tokenPrefix: string;
  createdAt: string;
  lastUsedAt: string | null;
  expiresAt: string | null;
  revoked: boolean;
}

export interface CreatedToken extends WebhookToken {
  /** Shown only once, at creation. */
  token: string;
  signingSecret: string;
}

// --- Runtime settings (Settings screen) ----------------------------------
// Mirror of backend/app/utils/app_settings.py::AppSettings. The GET returns the
// whole object; the POST takes the whole object back.

export interface AppSettings {
  corsOrigins: string[];
  rateLimitEnabled: boolean;
  rateLimitPerMinute: number;
  maxConcurrentJobsPerIp: number;
  maxImageSizeMb: number;
  sessionExpiryHours: number;
  previewMaxSize: number;
  astrodexCallbackUrls: string[];
  astrodexMaxRetries: number;
  astrodexRetryDelaySeconds: number;
  stackingEnabled: boolean;
  stackingMaxFrames: number;
  stackingRetentionHours: number;
  stackingWorkers: number;
  stackingWatchDir: string;
  stackingWatchIdleMinutes: number;
  stackingWatchAutoProcess: boolean;
  /** Optional operator-installed external ML engines, invoked as a subprocess.
   * Empty = off (docs/DEPLOYMENT.md "External ML engines"). */
  starnet2Path: string;
  deepsnrPath: string;
  starnet2Stride: number;
  deepsnrStride: number;
  logLevel: LogLevel;
  consoleLogLevel: LogLevel;
}

/** Result of probing one configured engine path (`GET /api/admin/engine-status`).
 * Mirror of `app/models/engines.py::EngineStatus`. */
export interface EngineStatus {
  configured: boolean;
  found: boolean;
  version: string | null;
  knownGood: boolean;
  detail: string;
}

export interface EngineStatusResponse {
  starnet2: EngineStatus;
  deepsnr: EngineStatus;
}

/** Non-sensitive runtime limits the UI needs before a session exists
 * (`GET /api/config`). Mirror of `app/routes/config.py::PublicConfig`. */
export interface PublicConfig {
  maxImageSizeMb: number;
  stackingEnabled: boolean;
  stackingMaxFrames: number;
  /** Star-removal engines the editor may offer. Always includes `'classic'`;
   * `'starnet2'` appears only when the operator has a working binary configured
   * (docs/DEPLOYMENT.md "External ML engines"). */
  starlessEngines: StarlessEngine[];
  /** Denoise engines, same rule: `'classic'` always, `'deepsnr'` when found. */
  denoiseEngines: DenoiseEngine[];
}

export type StarlessEngine = 'classic' | 'starnet2';
export type DenoiseEngine = 'classic' | 'deepsnr';

export type LogLevel = 'debug' | 'info' | 'warning' | 'error' | 'critical';

export interface LogLevels {
  file: LogLevel;
  console: LogLevel;
}

export interface LogTail {
  lines: string[];
  returned: number;
  filteredLevel: LogLevel | null;
}

// --- Depth shift -----------------------------------------------------------

/** Normalised (0-1) point in image space, e.g. where Depth Shift centers. */
export interface FocusPoint {
  x: number;
  y: number;
}

export interface DepthLayerInfo {
  layerId: number;
  depthRange: [number, number];
  imageUrl: string;
}

export interface DepthStatistics {
  minDepth: number;
  maxDepth: number;
  meanDepth: number;
  medianDepth: number;
  brightAreasPercent: number;
}

export interface DepthShiftResult {
  sessionId: string;
  numLayers: number;
  depthMapUrl: string;
  depthLayers: DepthLayerInfo[];
  statistics: DepthStatistics;
}

// --- Star mask preview -------------------------------------------------------

export interface StarSourceInfo {
  x: number; // fraction (0-1) of the analysed image's width
  y: number; // fraction (0-1) of the analysed image's height
  radius: number; // fraction (0-1) of the analysed image's longest side
}

export interface StarMaskResult {
  sessionId: string;
  sourceCount: number;
  stars: StarSourceInfo[];
}

// --- Update check -------------------------------------------------------------

/** GitHub's latest release for this repo, cached backend-side (see docs/API.md). */
export interface VersionCheckResult {
  currentVersion: string;
  latestVersion: string | null;
  updateAvailable: boolean;
  releaseUrl: string | null;
  releaseName: string | null;
  releaseNotes: string | null;
  publishedAt: string | null;
  error: string | null;
}

// --- Stacking (linear rebuild) ----------------------------------------------
// See initial_plan/12_STACKING_REBUILD.md.

export type CombinationMethod = 'average' | 'median';
export type RegistrationTransform = 'translation' | 'similarity' | 'affine';
export type RejectionAlgo = 'none' | 'sigma' | 'winsorized_sigma';
export type StackWeighting = 'none' | 'noise' | 'quality';
export type CalibrationKind = 'dark' | 'flat' | 'bias' | 'dark_flat';
export type QualityFilter = 'off' | 'lenient' | 'moderate' | 'strict';
export type DrizzleFactor = 1 | 2 | 3;

export interface StackSettings {
  registrationTransform: RegistrationTransform;
  combinationMethod: CombinationMethod;
  rejectionAlgo: RejectionAlgo;
  weighting: StackWeighting;
  cosmeticCorrection: boolean;
  qualityFilter: QualityFilter;
  postProcess: boolean;
  drizzleFactor: DrizzleFactor;
}

export interface FrameQuality {
  starCount: number;
  fwhm: number;
  roundness: number;
  background: number;
  snr: number;
  score: number; // 0..100
  weight: number;
  accepted: boolean;
  rejectReason: string | null; // "clouds" | "soft" | "trailed" | "bright_sky"
}

export interface CalibrationFrameCounts {
  dark: number;
  flat: number;
  bias: number;
  darkFlat: number;
}

export interface CalibrationSummary {
  frames: CalibrationFrameCounts;
  cosmeticCorrection: boolean;
}

export interface StackSession {
  stackId: string;
  status: string;
  frameCount: number;
  receivedFrames: number;
}

export interface UploadFrameResult {
  frameIndex: number;
  receivedFrames: number;
  frameCount: number;
  status: string;
}

/** One uploaded frame, for the frame grid. */
export interface StackFrameInfo {
  index: number;
  thumbUrl: string;
  excluded: boolean;
  quality: FrameQuality | null;
}

export interface StackStatistics {
  framesStacked: number;
  framesExcluded: number;
  framesAutoRejected: number;
  combinationMethod: string;
  registrationTransform: string;
  registrationRmsPx: number | null;
  referenceFrame: number | null;
  snrImprovement: number;
  measuredNoiseReduction: number | null;
  calibrated: boolean;
  postProcessed: boolean;
  drizzleFactor: number;
}

export interface StackResult {
  stackId: string;
  status: string;
  jobId?: string | null;
  wsStatusUrl?: string | null;
  sessionId: string | null;
  stackedImageUrl: string | null;
  statistics: StackStatistics | null;
  frames: StackFrameInfo[];
  calibration: CalibrationSummary | null;
  error: string | null;
}
