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

export interface ProcessingParameters {
  geometry: GeometryParameters;
  contrast: number;
  brightness: number;
  saturation: number;
  highlights: number;
  shadows: number;
  clarity: number;
  vibrance: number;
  denoise: number;
  starReduction: number;
  sharpness: number;
  temperature: number;
  tint: number;
  depthShiftIntensity: number;
}

export const DEFAULT_PARAMETERS: ProcessingParameters = {
  geometry: DEFAULT_GEOMETRY,
  contrast: 1.0,
  brightness: 0.0,
  saturation: 1.0,
  highlights: 0.0,
  shadows: 0.0,
  clarity: 0.0,
  vibrance: 1.0,
  denoise: 0,
  starReduction: 0,
  sharpness: 1.0,
  temperature: 6500,
  tint: 0,
  depthShiftIntensity: 0,
};

/** Numeric parameters driven by the slider panel (everything but `geometry`). */
export type SliderParameterKey = Exclude<keyof ProcessingParameters, 'geometry'>;

export interface ParameterBound {
  key: SliderParameterKey;
  label: string;
  min: number;
  max: number;
  step: number;
  group: 'basic' | 'tone' | 'noise' | 'star' | 'sharp' | 'color' | 'depth';
}

export const PARAMETER_BOUNDS: ParameterBound[] = [
  { key: 'contrast', label: 'Contrast', min: 0.5, max: 3.0, step: 0.01, group: 'basic' },
  { key: 'brightness', label: 'Brightness', min: -1.0, max: 1.0, step: 0.01, group: 'basic' },
  { key: 'highlights', label: 'Highlights', min: -1.0, max: 1.0, step: 0.01, group: 'tone' },
  { key: 'shadows', label: 'Shadows', min: -1.0, max: 1.0, step: 0.01, group: 'tone' },
  { key: 'clarity', label: 'Clarity', min: -1.0, max: 1.0, step: 0.01, group: 'tone' },
  { key: 'denoise', label: 'Denoise', min: 0, max: 100, step: 1, group: 'noise' },
  { key: 'starReduction', label: 'Star reduction', min: 0, max: 100, step: 1, group: 'star' },
  { key: 'sharpness', label: 'Sharpness', min: 0.0, max: 2.0, step: 0.01, group: 'sharp' },
  { key: 'vibrance', label: 'Vibrance', min: 0.0, max: 2.0, step: 0.01, group: 'sharp' },
  { key: 'saturation', label: 'Saturation', min: 0.0, max: 2.0, step: 0.01, group: 'color' },
  { key: 'temperature', label: 'Temperature', min: 2000, max: 8000, step: 50, group: 'color' },
  { key: 'tint', label: 'Tint', min: -50, max: 50, step: 1, group: 'color' },
  { key: 'depthShiftIntensity', label: 'Depth Shift', min: -100, max: 100, step: 1, group: 'depth' },
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
  maxImageSizeMb: number;
  sessionExpiryHours: number;
  previewMaxSize: number;
  astrodexCallbackUrls: string[];
  astrodexMaxRetries: number;
  astrodexRetryDelaySeconds: number;
  denoiseEnableMl: boolean;
  depthDetectionMethod: 'gradient' | 'ml';
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
