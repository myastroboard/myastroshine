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

export interface ProcessingParameters {
  geometry: GeometryParameters;
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
  chromaDenoise: number;
  vignetteCorrection: number;
  gradientReduction: number;
  dehaze: number;
  starReduction: number;
  starSensitivity: number;
  starMaxSize: number;
  sharpness: number;
  temperature: number;
  tint: number;
  depthShiftIntensity: number;
  curvePoints: CurvePoint[];
  redCurvePoints: CurvePoint[];
  greenCurvePoints: CurvePoint[];
  blueCurvePoints: CurvePoint[];
}

export const DEFAULT_PARAMETERS: ProcessingParameters = {
  geometry: DEFAULT_GEOMETRY,
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
  chromaDenoise: 0,
  vignetteCorrection: 0,
  gradientReduction: 0,
  dehaze: 0,
  starReduction: 0,
  starSensitivity: 50,
  starMaxSize: 30,
  sharpness: 1.0,
  temperature: 6500,
  tint: 0,
  depthShiftIntensity: 0,
  curvePoints: [], // empty = no curve (identity); the editor shows DEFAULT_CURVE_POINTS instead
  redCurvePoints: [],
  greenCurvePoints: [],
  blueCurvePoints: [],
};

/** Curve fields, keyed by the channel the ToneCurveEditor tab selector edits. */
export const CURVE_CHANNELS = ['rgb', 'red', 'green', 'blue'] as const;
export type CurveChannel = (typeof CURVE_CHANNELS)[number];

export const CURVE_CHANNEL_FIELD: Record<CurveChannel, keyof ProcessingParameters> = {
  rgb: 'curvePoints',
  red: 'redCurvePoints',
  green: 'greenCurvePoints',
  blue: 'blueCurvePoints',
};

/** Numeric parameters driven by the slider panel (everything but geometry / curve fields). */
export type SliderParameterKey = Exclude<
  keyof ProcessingParameters,
  'geometry' | 'curvePoints' | 'redCurvePoints' | 'greenCurvePoints' | 'blueCurvePoints'
>;

export interface ParameterBound {
  key: SliderParameterKey;
  min: number;
  max: number;
  step: number;
  group: 'light' | 'corrections' | 'colour' | 'detail' | 'star' | 'depth';
}

/**
 * Label and hint text live in the i18n translation files, keyed by `key`
 * (`slider_panel.params.<key>.label` / `.hint`), not here - see SliderPanel.tsx.
 */
export const PARAMETER_BOUNDS: ParameterBound[] = [
  { key: 'contrast', min: 0.5, max: 3.0, step: 0.01, group: 'light' },
  { key: 'exposure', min: -1.0, max: 1.0, step: 0.01, group: 'light' },
  { key: 'highlights', min: -1.0, max: 1.0, step: 0.01, group: 'light' },
  { key: 'shadows', min: -1.0, max: 1.0, step: 0.01, group: 'light' },
  { key: 'whites', min: -1.0, max: 1.0, step: 0.01, group: 'light' },
  { key: 'blacks', min: -1.0, max: 1.0, step: 0.01, group: 'light' },
  { key: 'vignetteCorrection', min: 0, max: 100, step: 1, group: 'corrections' },
  { key: 'gradientReduction', min: 0, max: 100, step: 1, group: 'corrections' },
  { key: 'dehaze', min: 0, max: 100, step: 1, group: 'corrections' },
  { key: 'clarity', min: -1.0, max: 1.0, step: 0.01, group: 'detail' },
  { key: 'denoise', min: 0, max: 100, step: 1, group: 'detail' },
  { key: 'chromaDenoise', min: 0, max: 100, step: 1, group: 'detail' },
  { key: 'starReduction', min: 0, max: 100, step: 1, group: 'star' },
  { key: 'starSensitivity', min: 0, max: 100, step: 1, group: 'star' },
  { key: 'starMaxSize', min: 0, max: 100, step: 1, group: 'star' },
  { key: 'sharpness', min: 0.0, max: 2.0, step: 0.01, group: 'detail' },
  { key: 'vibrance', min: 0.0, max: 2.0, step: 0.01, group: 'colour' },
  { key: 'saturation', min: 0.0, max: 2.0, step: 0.01, group: 'colour' },
  { key: 'temperature', min: 2000, max: 8000, step: 50, group: 'colour' },
  { key: 'tint', min: -50, max: 50, step: 1, group: 'colour' },
  { key: 'depthShiftIntensity', min: -100, max: 100, step: 1, group: 'depth' },
];

export interface Image {
  sessionId: string;
  originalUrl: string;
  processedUrl: string;
  width: number;
  height: number;
  fileSize: number;
}

export interface UploadResponse {
  sessionId: string;
  imageUrl: string;
  dimensions: Dimensions;
  fileSizeBytes: number;
  histogram: HistogramData;
  uploadTimestamp: string;
  expiresAt: string;
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
}

export type JobStatus = 'queued' | 'processing' | 'completed' | 'failed';

export interface ProcessingStatus {
  jobId: string;
  status: JobStatus;
  progressPercent: number;
  currentStep: string;
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

export interface WebhookResponse {
  webhookId: string;
  status: 'pending' | 'sent' | 'failed';
  message: string;
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
  stackingDetector: 'orb' | 'sift';
  stackingCombinationDefault: CombinationMethod;
  stackingCosmicRayThreshold: number;
  logLevel: LogLevel;
  consoleLogLevel: LogLevel;
}

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

// --- Stacking (v1.1) ---------------------------------------------------------

export type CombinationMethod = 'median' | 'mean' | 'sigma_clip';
export type RegistrationMethod = 'sift' | 'orb';

export interface StackSettings {
  registrationMethod: RegistrationMethod;
  combinationMethod: CombinationMethod;
  cosmicRayRejection: boolean;
  backgroundNormalization: boolean;
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

export interface StackStatistics {
  framesStacked: number;
  framesRejected: number;
  combinationMethod: string;
  cosmicRaysRemoved: number;
  registrationSuccessRate: number;
  snrImprovement: number;
}

export interface StackResult {
  stackId: string;
  status: string;
  jobId?: string | null;
  wsStatusUrl?: string | null;
  sessionId: string | null;
  stackedImageUrl: string | null;
  statistics: StackStatistics | null;
  error: string | null;
}
