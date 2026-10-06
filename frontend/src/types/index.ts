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
/** How the Stack step stretches the linear composite: `'adaptive'` is the
 * colour-preserving stretch fitted to the image's sky and object levels,
 * `'classic'` the original per-channel auto-stretch (kept for comparison). */
export type StretchMode = 'adaptive' | 'classic';

export const STRETCH_MODES: StretchMode[] = ['adaptive', 'classic'];

export interface StackParameters {
  /** Auto-stretch intensity: 0 = subtle (dark sky), 1 = aggressive. */
  stretch: number;
  stretchMode: StretchMode;
  /** How much of the fitted low-order sky gradient to remove (0 = off, 100 = full). */
  backgroundExtraction: number;
  /** Neutralise the sky background and white-balance on the star field. */
  colorCalibration: boolean;
}

export const DEFAULT_STACK_PARAMETERS: StackParameters = {
  stretch: 0.5,
  stretchMode: 'adaptive',
  backgroundExtraction: 100,
  colorCalibration: true,
};

export function stackParametersEqual(a: StackParameters, b: StackParameters): boolean {
  return (
    a.stretch === b.stretch &&
    a.stretchMode === b.stretchMode &&
    a.backgroundExtraction === b.backgroundExtraction &&
    a.colorCalibration === b.colorCalibration
  );
}

/**
 * The optional "Style" finishing look, applied last (backend
 * `app/services/looks.py`). Every look only reworks the recorded light - tone,
 * colour, contrast, a glow from the image's own bright areas - never adds stars
 * or detail. `lookId: null` (the default) is no look at all.
 */
export type LookId =
  | 'vivid'
  | 'soft_glow'
  | 'cinematic'
  | 'galactic_core'
  | 'blue_hour'
  | 'luminous'
  | 'structure'
  | 'deep_field'
  | 'warm_core'
  | 'sparkle'
  | 'night_velvet'
  | 'moon_crisp'
  | 'moonlight'
  | 'planet_crisp'
  | 'rich_colour';

/** Kinds of picture the gallery groups its looks by. `'nightscape'` only when
 * the photo has a sky mask (a night landscape - its looks treat the sky and the
 * ground apart). */
export type LookScene =
  | 'general'
  | 'nightscape'
  | 'nebula'
  | 'galaxy'
  | 'cluster'
  | 'moon'
  | 'planet';

export interface LookGroup {
  scene: LookScene;
  looks: LookId[];
}

/** `GET /api/looks/{id}`: the gallery's groups in display order, and the group
 * it opens on. */
export interface LookCatalog {
  scene: LookScene;
  groups: LookGroup[];
}

/** Every session's groups (no night landscape) - also the gallery's fallback
 * before the catalogue loads. */
export const DEFAULT_LOOK_CATALOG: LookCatalog = {
  scene: 'general',
  groups: [
    { scene: 'general', looks: ['vivid', 'soft_glow', 'cinematic'] },
    { scene: 'nebula', looks: ['luminous', 'structure'] },
    { scene: 'galaxy', looks: ['deep_field', 'warm_core'] },
    { scene: 'cluster', looks: ['sparkle', 'night_velvet'] },
    { scene: 'moon', looks: ['moon_crisp', 'moonlight'] },
    { scene: 'planet', looks: ['planet_crisp', 'rich_colour'] },
  ],
};

/** The gallery group a built-in preset points at: the user said what they shot
 * by picking it, so the Style step opens there (the kind of target is never
 * guessed from the picture). */
export const PRESET_LOOK_SCENE: Readonly<Record<string, LookScene>> = {
  system_nebula: 'nebula',
  system_galaxy: 'galaxy',
  system_cluster: 'cluster',
  system_lunar: 'moon',
};

export interface LookParameters {
  lookId: LookId | null;
  /** How strongly the look applies, 0-100 (0 = no effect). */
  amount: number;
}

export const DEFAULT_LOOK_AMOUNT = 60;

export const DEFAULT_LOOK_PARAMETERS: LookParameters = {
  lookId: null,
  amount: DEFAULT_LOOK_AMOUNT,
};

export function lookParametersEqual(a: LookParameters, b: LookParameters): boolean {
  return a.lookId === b.lookId && a.amount === b.amount;
}

export interface ProcessingParameters {
  geometry: GeometryParameters;
  stack: StackParameters;
  look: LookParameters;
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
  /** SCNR green removal, 0 (off) - 100 (green capped at the red/blue mean). */
  greenRemoval: number;
  curvePoints: CurvePoint[];
  redCurvePoints: CurvePoint[];
  greenCurvePoints: CurvePoint[];
  blueCurvePoints: CurvePoint[];
}

export const DEFAULT_PARAMETERS: ProcessingParameters = {
  geometry: DEFAULT_GEOMETRY,
  stack: DEFAULT_STACK_PARAMETERS,
  look: DEFAULT_LOOK_PARAMETERS,
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
  greenRemoval: 0,
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
  if (!lookParametersEqual(p.look, DEFAULT_LOOK_PARAMETERS)) {
    return true;
  }
  for (const key of Object.keys(DEFAULT_PARAMETERS) as (keyof ProcessingParameters)[]) {
    if (key === 'geometry' || key === 'stack' || key === 'look') {
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
  if (!lookParametersEqual(a.look, b.look)) {
    return false;
  }
  for (const key of Object.keys(DEFAULT_PARAMETERS) as (keyof ProcessingParameters)[]) {
    if (key === 'geometry' || key === 'stack' || key === 'look') {
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
 * look / curve fields, and the discrete engine choices, which are pickers, not sliders). */
export type SliderParameterKey = Exclude<
  keyof ProcessingParameters,
  | 'geometry'
  | 'stack'
  | 'look'
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
  { key: 'contrast', min: 0.5, max: 3.0, step: 0.1 },
  { key: 'exposure', min: -1.0, max: 1.0, step: 0.1 },
  { key: 'highlights', min: -1.0, max: 1.0, step: 0.1 },
  { key: 'shadows', min: -1.0, max: 1.0, step: 0.1 },
  { key: 'whites', min: -1.0, max: 1.0, step: 0.1 },
  { key: 'blacks', min: -1.0, max: 1.0, step: 0.1 },
  { key: 'vignetteCorrection', min: -100, max: 100, step: 1 },
  { key: 'gradientReduction', min: 0, max: 100, step: 1 },
  { key: 'dehaze', min: 0, max: 100, step: 1 },
  { key: 'clarity', min: -1.0, max: 1.0, step: 0.1 },
  { key: 'denoise', min: 0, max: 100, step: 1 },
  { key: 'chromaDenoise', min: 0, max: 100, step: 1 },
  { key: 'starReduction', min: 0, max: 100, step: 1 },
  { key: 'starSensitivity', min: 0, max: 100, step: 1 },
  { key: 'starMaxSize', min: 0, max: 100, step: 1 },
  { key: 'starRemoval', min: 0, max: 100, step: 1 },
  { key: 'starRecombine', min: 0, max: 100, step: 1 },
  { key: 'sharpness', min: 0.0, max: 2.0, step: 0.1 },
  { key: 'vibrance', min: 0.0, max: 2.0, step: 0.1 },
  { key: 'saturation', min: 0.0, max: 2.0, step: 0.1 },
  { key: 'temperature', min: 2000, max: 8000, step: 50 },
  { key: 'tint', min: -50, max: 50, step: 1 },
  { key: 'greenRemoval', min: 0, max: 100, step: 1 },
];

export const PARAMETER_BOUND_BY_KEY: Partial<Record<SliderParameterKey, ParameterBound>> =
  Object.fromEntries(PARAMETER_BOUNDS.map((bound) => [bound.key, bound]));

/**
 * White-balance temperature snaps to these standard Kelvin values - the slider
 * is a discrete index over them rather than a free 2000-8000 K ramp. Lower K
 * warms the image (amber), higher K cools it (blue); {@link NEUTRAL_TEMPERATURE}
 * is the no-op. The backend still accepts any value in range (an older preset,
 * a direct API call), so {@link temperatureIndex} maps one to the nearest stop.
 */
export const STANDARD_TEMPERATURES = [
  2000, 3200, 4500, 5500, 6000, 6500, 7000, 7500, 8000,
] as const;

export const NEUTRAL_TEMPERATURE = 6500;

/** Index of the standard value nearest `kelvin` (ties resolve to the warmer stop). */
export function temperatureIndex(kelvin: number): number {
  let best = 0;
  for (let i = 1; i < STANDARD_TEMPERATURES.length; i += 1) {
    if (Math.abs(STANDARD_TEMPERATURES[i] - kelvin) < Math.abs(STANDARD_TEMPERATURES[best] - kelvin)) {
      best = i;
    }
  }
  return best;
}

/**
 * The editor workflow, in retouching order. This mirrors the backend pipeline
 * order in `app/services/image_processing.py::apply_parameters`: geometry first,
 * then white balance and background corrections, then tone, curves, colour,
 * detail, then stars (reduce in place, or remove entirely - `star_removal`
 * splits the backend pipeline; see that method). The rail, the inspector panel
 * switch, and the "modified" dots all derive from this one list.
 *
 * `start` and `export` are workflow brackets (no step number): a one-click
 * starting point, and getting the result out. `style` is the optional finishing
 * look just before export - the backend runs it last, after every other stage.
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
  | 'style'
  | 'export';

/**
 * The rail groups the steps into phases so eleven tools read as four moves:
 * begin (one-click start), prepare the raw image, enhance it, finish it - then
 * deliver. Labels live in `editor.rail.phase.<phase>`.
 */
export type EditorPhase = 'begin' | 'prepare' | 'enhance' | 'finish' | 'deliver';

export interface EditorStep {
  id: EditorStepId;
  /** Which rail group the step sits in. */
  phase: EditorPhase;
  /** Slider parameters shown in this step's panel, in display order. */
  params: SliderParameterKey[];
  /** Only shown for a stacked-composite session. */
  stackOnly?: boolean;
}

export const EDITOR_STEPS: EditorStep[] = [
  // 'stack' before 'start': a composite session opens straight on 'stack' (see
  // EditorView's initial activeStep), and Auto Astro (on 'start') analyses the
  // rendered image - it belongs *after* the stack render is dialled in, not
  // before. This order also drives the inspector's "next step" button.
  { id: 'stack', phase: 'begin', params: [], stackOnly: true },
  { id: 'start', phase: 'begin', params: [] },
  { id: 'frame', phase: 'prepare', params: [] },
  {
    id: 'sky',
    phase: 'prepare',
    params: [
      'temperature',
      'tint',
      'greenRemoval',
      'vignetteCorrection',
      'gradientReduction',
      'dehaze',
    ],
  },
  {
    id: 'light',
    phase: 'enhance',
    params: ['exposure', 'contrast', 'highlights', 'shadows', 'whites', 'blacks'],
  },
  { id: 'curves', phase: 'enhance', params: [] },
  { id: 'colour', phase: 'enhance', params: ['saturation', 'vibrance'] },
  { id: 'detail', phase: 'finish', params: ['clarity', 'denoise', 'chromaDenoise', 'sharpness'] },
  {
    id: 'stars',
    phase: 'finish',
    // Reduce (shrink in place), remove (starless split + recombine), and the
    // shared detection controls - all rendered as one grouped panel, see
    // EditorInspector's StarsPanel.
    params: ['starReduction', 'starRemoval', 'starRecombine', 'starSensitivity', 'starMaxSize'],
  },
  { id: 'depth', phase: 'finish', params: [] },
  { id: 'style', phase: 'deliver', params: [] },
  { id: 'export', phase: 'deliver', params: [] },
];

/** True when a step's controls hold different values in two edit states - the
 * rail's "modified" dot (against the defaults) and the names given to the
 * editor's go-back points (against the previous point). */
export function stepChanged(
  step: EditorStep,
  a: ProcessingParameters,
  b: ProcessingParameters,
  focalA: FocusPoint | null,
  focalB: FocusPoint | null,
): boolean {
  switch (step.id) {
    case 'start':
    case 'export':
      return false;
    case 'stack':
      return !stackParametersEqual(a.stack, b.stack);
    case 'frame':
      return !geometryEquals(a.geometry, b.geometry);
    case 'style':
      // Only a chosen look counts: the amount alone, with no look, changes nothing.
      return a.look.lookId !== b.look.lookId || (b.look.lookId !== null && a.look.amount !== b.look.amount);
    case 'curves':
      return (
        !curvePointsEqual(a.curvePoints, b.curvePoints) ||
        !curvePointsEqual(a.redCurvePoints, b.redCurvePoints) ||
        !curvePointsEqual(a.greenCurvePoints, b.greenCurvePoints) ||
        !curvePointsEqual(a.blueCurvePoints, b.blueCurvePoints)
      );
    case 'depth':
      return focalA === null || focalB === null
        ? focalA !== focalB
        : focalA.x !== focalB.x || focalA.y !== focalB.y;
    default:
      return step.params.some((key) => a[key] !== b[key]);
  }
}

/** True when a step's controls hold a value that differs from the default. */
export function stepIsModified(
  step: EditorStep,
  parameters: ProcessingParameters,
  focalPoint: FocusPoint | null,
): boolean {
  return stepChanged(step, DEFAULT_PARAMETERS, parameters, null, focalPoint);
}

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

/** Acquisition info read off the source FITS header(s) - every field is
 * best-effort and may be absent or `null` (the API sends `null` for what the
 * header did not have). `null` as a whole when the session has none (an
 * ordinary photo, or a FITS with no usable header). */
export interface CaptureInfo {
  objectName?: string | null;
  telescope?: string | null;
  filter?: string | null;
  frameCount?: number | null;
  exposureS?: number | null;
  totalExposureS?: number | null;
  dateObs?: string | null;
  gain?: number | null;
  sensorTempC?: number | null;
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
   * the Export step's filename field. Absent for stacks and Astrodex handoffs. */
  originalFilename?: string;
  /** True when the session is a stacked composite - unlocks the "Stack" step. */
  isStack?: boolean;
  /** Set when the session was opened from an Astrodex handoff - unlocks the
   * "Send back to Astrodex" action in the Export step. */
  astrodex?: AstroDexReturn;
}

/** What the editor needs to send the enhanced result back to Astrodex. */
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

/** `GET /api/auth/status` - which admin gate the Settings page shows. */
export interface AuthStatus {
  /** `false`: the structural `ADMIN_ENABLED` switch turned the admin API off. */
  adminEnabled: boolean;
  /** `false`: no admin password yet - show the setup form. */
  configured: boolean;
  /** This browser holds a live admin session. */
  authenticated: boolean;
}

/** One logged-in admin browser (`GET /api/auth/sessions`). */
export interface AdminSession {
  id: string;
  clientIp: string | null;
  userAgent: string | null;
  createdAt: string;
  lastSeenAt: string;
  /** The session making the request. */
  current: boolean;
}

export interface AppSettings {
  /** An admin login stays valid this many days without use (max 30). */
  adminSessionIdleDays: number;
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
  /** How long a finished job (completed / failed / superseded) is kept before
   * the hourly cleanup prunes it. Hours. */
  jobHistoryRetentionHours: number;
}

/** Result of probing one configured engine path (`GET /api/admin/engine-status`).
 * Mirror of `app/models/engines.py::EngineStatus`. */
export interface EngineStatus {
  configured: boolean;
  found: boolean;
  version: string | null;
  knownGood: boolean;
  detail: string;
  /** Set when the package was uploaded from Settings (`null`: a manual path, or none). */
  installed?: InstalledEngine | null;
}

/** An engine package installed by uploading it from Settings. */
export interface InstalledEngine {
  version: string | null;
  archiveName: string;
  licenseAcceptedAt: string;
  path: string;
}

export type ExternalEngine = 'starnet2' | 'deepsnr';

/** An uploaded engine package, unpacked and checked, waiting for its licence to
 * be accepted (`POST /api/admin/engines/{engine}/stage`). */
export interface StagedEngine {
  stagingId: string;
  engine: ExternalEngine;
  archiveName: string;
  status: EngineStatus;
  licenseText: string;
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

// --- Job history / disk usage (Settings -> Operations) ---------------------

/** One row of `GET /api/admin/jobs`. */
export interface JobSummary {
  jobId: string;
  sessionId: string | null;
  status: string;
  progressPercent: number;
  currentStep: string | null;
  error: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface JobListResult {
  jobs: JobSummary[];
  total: number;
  limit: number;
  offset: number;
}

/** `GET /api/admin/disk-usage` - filesystem totals plus how the app's own
 * data splits across images, stacks, the database, and log files. */
export interface DiskUsage {
  totalBytes: number;
  usedBytes: number;
  freeBytes: number;
  imagesBytes: number;
  stacksBytes: number;
  dbBytes: number;
  logsBytes: number;
}

// --- Backup / restore (Settings -> Advanced) --------------------------------

/** A user preset in export/import shape - no `presetId` / `author` /
 * `isFavorite`; a fresh id is minted on import. */
export interface ConfigExportPreset {
  name: string;
  description: string | null;
  category: string;
  parameters: ProcessingParameters;
}

/** `GET /api/admin/config-export` - settings + every *user* preset (never the
 * 5 built-ins), bundled into one downloadable file. */
export interface ConfigExport {
  formatVersion: number;
  appVersion: string;
  exportedAt: string;
  settings: AppSettings;
  presets: ConfigExportPreset[];
}

/** `POST /api/admin/config-import` result. */
export interface ConfigImportResult {
  presetsImported: number;
  /** Names skipped because a preset with that name already existed - never
   * overwritten, never renamed. */
  presetsSkipped: string[];
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
