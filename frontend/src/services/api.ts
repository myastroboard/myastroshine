// HTTP client for the MyAstroShine backend.
// One method per API endpoint; see docs/API.md for the contracts.
//
// The backend uses snake_case; request bodies and responses are converted at
// this boundary (see caseConvert.ts) so the rest of the app stays camelCase.

import type {
  AppSettings,
  AutoAstroResult,
  CalibrationKind,
  CalibrationSummary,
  CreatedToken,
  DepthShiftResult,
  FocusPoint,
  LogLevel,
  LogLevels,
  LogTail,
  Preset,
  ProcessResponse,
  ProcessingParameters,
  PublicConfig,
  StackFrameInfo,
  StackResult,
  StackSession,
  StackSettings,
  StarMaskResult,
  UploadFrameResult,
  UploadResponse,
  VersionCheckResult,
  WebhookResponse,
  WebhookToken,
} from '@/types';

import { keysToCamelCase, keysToSnakeCase } from './caseConvert';

const API_URL = import.meta.env.VITE_API_URL ?? '/api';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function readError(response: Response): Promise<ApiError> {
  const text = await response.text();
  try {
    const body = JSON.parse(text) as { error?: string };
    return new ApiError(response.status, body.error ?? text);
  } catch {
    return new ApiError(response.status, text || response.statusText);
  }
}

interface RequestOptions {
  method?: string;
  json?: unknown;
  bearer?: string;
}

/**
 * POST a `FormData` body with upload-progress reporting. `fetch` cannot report
 * request-body progress, so uploads that can be large (a full-res FITS / RAW)
 * go through `XMLHttpRequest` instead. `onProgress` receives a 0-1 fraction and
 * only fires while the browser can measure the transfer (`lengthComputable`).
 */
function uploadWithProgress<T>(
  path: string,
  form: FormData,
  onProgress?: (fraction: number) => void,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_URL}${path}`);
    if (onProgress) {
      xhr.upload.addEventListener('progress', (event) => {
        if (event.lengthComputable) {
          onProgress(event.loaded / event.total);
        }
      });
    }
    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(keysToCamelCase<T>(JSON.parse(xhr.responseText)));
        } catch {
          reject(new ApiError(xhr.status, 'Malformed server response'));
        }
        return;
      }
      let message = xhr.responseText || xhr.statusText;
      try {
        message = (JSON.parse(xhr.responseText) as { error?: string }).error ?? message;
      } catch {
        /* not JSON - keep the raw text */
      }
      reject(new ApiError(xhr.status, message));
    });
    xhr.addEventListener('error', () => reject(new ApiError(0, 'Network error during upload')));
    xhr.addEventListener('abort', () => reject(new ApiError(0, 'Upload cancelled')));
    xhr.send(form);
  });
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const init: RequestInit = { method: options.method ?? 'GET', headers };
  if (options.json !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(keysToSnakeCase(options.json));
  }
  if (options.bearer) {
    headers.Authorization = `Bearer ${options.bearer}`;
  }

  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) {
    throw await readError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return keysToCamelCase<T>(await response.json());
}

export interface SavePresetInput {
  name: string;
  category?: string;
  description?: string;
  parameters: ProcessingParameters;
}

interface SavePresetResult {
  presetId: string;
  name: string;
  createdAt: string;
}

export const apiClient = {
  /** `onProgress` reports the byte-transfer fraction (0-1); the server then
   * decodes the image before responding, which this cannot measure. */
  uploadImage(
    file: File,
    onProgress?: (fraction: number) => void,
  ): Promise<UploadResponse> {
    const form = new FormData();
    form.append('file', file);
    return uploadWithProgress<UploadResponse>('/upload', form, onProgress);
  },

  processImage(sessionId: string, parameters: ProcessingParameters): Promise<ProcessResponse> {
    return request<ProcessResponse>(`/process/${sessionId}`, {
      method: 'POST',
      json: { parameters },
    });
  },

  /**
   * URL for a session image.
   * - `original`: the untouched upload (before/after "before" side)
   * - `geometry`: with `original`, apply the session's current crop/rotate/
   *   flip/straighten (but no colour/tone enhancement) - keeps the "before"
   *   side aligned with the result's frame once geometry has changed it
   * - `full`: full-resolution current result (default: downscaled preview)
   * - `v`: cache-busting token; bump it when the result changes so the
   *   browser re-fetches an otherwise-identical URL.
   */
  previewUrl(
    sessionId: string,
    opts: { full?: boolean; original?: boolean; geometry?: boolean; v?: number | string } = {},
  ): string {
    const params = new URLSearchParams();
    if (opts.original) {
      params.set('original', 'true');
      if (opts.geometry) {
        params.set('geometry', 'true');
      }
    } else if (opts.full) {
      params.set('full', 'true');
    }
    if (opts.v !== undefined) {
      params.set('v', String(opts.v));
    }
    const query = params.toString();
    return `${API_URL}/preview/${sessionId}${query ? `?${query}` : ''}`;
  },

  async downloadImage(sessionId: string, format = 'jpeg', quality = 95): Promise<Blob> {
    const response = await fetch(`${API_URL}/download/${sessionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ format, quality }),
    });
    if (!response.ok) {
      throw await readError(response);
    }
    return response.blob();
  },

  sendToAstroDex(
    sessionId: string,
    astrodexImageId: string,
    callbackUrl: string,
    token: string,
  ): Promise<WebhookResponse> {
    return request<WebhookResponse>('/send-to-astrodex', {
      method: 'POST',
      bearer: token,
      json: { sessionId, astrodexImageId, astrodexCallbackUrl: callbackUrl },
    });
  },

  // --- Runtime settings (Settings screen) ---
  getAppSettings(): Promise<AppSettings> {
    return request<AppSettings>('/admin/app-settings');
  },

  saveAppSettings(settings: AppSettings): Promise<AppSettings> {
    return request<AppSettings>('/admin/app-settings', { method: 'POST', json: settings });
  },

  // --- Logs (Settings -> Logs) ---
  getLogs(limit = 300, level?: LogLevel): Promise<LogTail> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (level) {
      params.set('level', level);
    }
    return request<LogTail>(`/admin/logs?${params.toString()}`);
  },

  getLogLevels(): Promise<LogLevels> {
    return request<LogLevels>('/admin/logs/level');
  },

  clearLogs(): Promise<void> {
    return request<void>('/admin/logs/clear', { method: 'POST' });
  },

  async exportLogs(): Promise<Blob> {
    const response = await fetch(`${API_URL}/admin/logs/export`);
    if (!response.ok) {
      throw await readError(response);
    }
    return response.blob();
  },

  // --- Webhook tokens (created from Settings) ---
  listTokens(): Promise<{ tokens: WebhookToken[]; total: number }> {
    return request('/tokens');
  },

  createToken(name: string, expiresInDays?: number): Promise<CreatedToken> {
    return request<CreatedToken>('/tokens', {
      method: 'POST',
      json: { name, expiresInDays },
    });
  },

  revokeToken(tokenId: string): Promise<void> {
    return request<void>(`/tokens/${tokenId}`, { method: 'DELETE' });
  },

  listPresets(): Promise<{ presets: Preset[]; total: number }> {
    return request('/presets');
  },

  savePreset(preset: SavePresetInput): Promise<SavePresetResult> {
    return request<SavePresetResult>('/presets', { method: 'POST', json: preset });
  },

  deletePreset(presetId: string): Promise<void> {
    return request<void>(`/presets/${presetId}`, { method: 'DELETE' });
  },

  applyPreset(presetId: string, sessionId: string): Promise<ProcessResponse> {
    return request<ProcessResponse>(`/presets/${presetId}/apply/${sessionId}`, { method: 'POST' });
  },

  applyAutoAstro(sessionId: string): Promise<AutoAstroResult> {
    return request<AutoAstroResult>(`/auto-astro/${sessionId}`, { method: 'POST' });
  },

  generateDepthShift(
    sessionId: string,
    numLayers = 7,
    intensity = 50,
    focusPoint?: FocusPoint,
  ): Promise<DepthShiftResult> {
    return request<DepthShiftResult>(`/depth-shift/${sessionId}`, {
      method: 'POST',
      json: { numLayers, intensity, ...(focusPoint ? { focusPoint } : {}) },
    });
  },

  detectStars(sessionId: string, sensitivity: number, maxSize: number): Promise<StarMaskResult> {
    return request<StarMaskResult>(`/star-mask/${sessionId}`, {
      method: 'POST',
      json: { sensitivity, maxSize },
    });
  },

  // --- Stacking (v1.1) ---
  initiateStack(frameCount: number, settings: StackSettings): Promise<StackSession> {
    return request<StackSession>('/stack/initiate', {
      method: 'POST',
      json: { frameCount, ...settings },
    });
  },

  async uploadStackFrame(
    stackId: string,
    frameIndex: number,
    file: File,
  ): Promise<UploadFrameResult> {
    const form = new FormData();
    form.append('frame_index', String(frameIndex));
    form.append('file', file);
    const response = await fetch(`${API_URL}/stack/${stackId}/upload-frame`, {
      method: 'POST',
      body: form,
    });
    if (!response.ok) {
      throw await readError(response);
    }
    return keysToCamelCase<UploadFrameResult>(await response.json());
  },

  async uploadStackFrames(
    stackId: string,
    startIndex: number,
    files: File[],
  ): Promise<StackSession> {
    const form = new FormData();
    form.append('start_index', String(startIndex));
    for (const file of files) {
      form.append('files', file);
    }
    const response = await fetch(`${API_URL}/stack/${stackId}/upload-frames`, {
      method: 'POST',
      body: form,
    });
    if (!response.ok) {
      throw await readError(response);
    }
    return keysToCamelCase<StackSession>(await response.json());
  },

  async uploadStackArchive(stackId: string, file: File): Promise<StackSession> {
    const form = new FormData();
    form.append('file', file);
    const response = await fetch(`${API_URL}/stack/${stackId}/upload-archive`, {
      method: 'POST',
      body: form,
    });
    if (!response.ok) {
      throw await readError(response);
    }
    return keysToCamelCase<StackSession>(await response.json());
  },

  excludeStackFrame(stackId: string, index: number, excluded: boolean): Promise<StackFrameInfo> {
    return request<StackFrameInfo>(`/stack/${stackId}/frame/${index}/exclude`, {
      method: 'POST',
      json: { excluded },
    });
  },

  async uploadCalibrationFrames(
    stackId: string,
    kind: CalibrationKind,
    files: File[],
  ): Promise<CalibrationSummary> {
    const form = new FormData();
    for (const file of files) {
      form.append('files', file);
    }
    const response = await fetch(`${API_URL}/stack/${stackId}/calibration/${kind}/frames`, {
      method: 'POST',
      body: form,
    });
    if (!response.ok) {
      throw await readError(response);
    }
    return keysToCamelCase<CalibrationSummary>(await response.json());
  },

  clearCalibration(stackId: string, kind: CalibrationKind): Promise<CalibrationSummary> {
    return request<CalibrationSummary>(`/stack/${stackId}/calibration/${kind}`, {
      method: 'DELETE',
    });
  },

  processStack(stackId: string, overrides?: StackSettings): Promise<StackResult> {
    return request<StackResult>(`/stack/${stackId}/process`, {
      method: 'POST',
      json: overrides,
    });
  },

  getStack(stackId: string): Promise<StackResult> {
    return request<StackResult>(`/stack/${stackId}`);
  },

  // --- Update check ---
  checkForUpdates(): Promise<VersionCheckResult> {
    return request<VersionCheckResult>('/version/check-updates');
  },

  /** Public runtime limits (upload size cap, stacking limits). */
  getConfig(): Promise<PublicConfig> {
    return request<PublicConfig>('/config');
  },
};

export type ApiClient = typeof apiClient;
