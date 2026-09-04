// HTTP client for the MyAstroShine backend.
// One method per API endpoint; see docs/API.md for the contracts.
//
// The backend uses snake_case; request bodies and responses are converted at
// this boundary (see caseConvert.ts) so the rest of the app stays camelCase.

import type {
  AppSettings,
  CreatedToken,
  DepthShiftResult,
  LogLevel,
  LogLevels,
  LogTail,
  Preset,
  ProcessResponse,
  ProcessingParameters,
  StackResult,
  StackSession,
  StackSettings,
  UploadFrameResult,
  UploadResponse,
  WebhookResponse,
  WebhookToken,
} from '@/types';

import { keysToCamelCase, keysToSnakeCase } from './caseConvert';

const API_URL = import.meta.env.VITE_API_URL ?? '/api';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly errorCode?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function readError(response: Response): Promise<ApiError> {
  const text = await response.text();
  try {
    const body = JSON.parse(text) as { error?: string; error_code?: string };
    return new ApiError(response.status, body.error ?? text, body.error_code);
  } catch {
    return new ApiError(response.status, text || response.statusText);
  }
}

interface RequestOptions {
  method?: string;
  json?: unknown;
  bearer?: string;
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

export interface SavePresetResult {
  presetId: string;
  name: string;
  createdAt: string;
}

export const apiClient = {
  async uploadImage(file: File): Promise<UploadResponse> {
    const form = new FormData();
    form.append('file', file);
    const response = await fetch(`${API_URL}/upload`, { method: 'POST', body: form });
    if (!response.ok) {
      throw await readError(response);
    }
    return keysToCamelCase<UploadResponse>(await response.json());
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
   * - `full`: full-resolution current result (default: downscaled preview)
   * - `v`: cache-busting token; bump it when the result changes so the
   *   browser re-fetches an otherwise-identical URL.
   */
  previewUrl(
    sessionId: string,
    opts: { full?: boolean; original?: boolean; v?: number | string } = {},
  ): string {
    const params = new URLSearchParams();
    if (opts.original) {
      params.set('original', 'true');
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

  generateDepthShift(
    sessionId: string,
    numLayers = 7,
    intensity = 50,
  ): Promise<DepthShiftResult> {
    return request<DepthShiftResult>(`/depth-shift/${sessionId}`, {
      method: 'POST',
      json: { numLayers, intensity },
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

  processStack(stackId: string): Promise<StackResult> {
    return request<StackResult>(`/stack/${stackId}/process`, { method: 'POST' });
  },

  getStack(stackId: string): Promise<StackResult> {
    return request<StackResult>(`/stack/${stackId}`);
  },
};

export type ApiClient = typeof apiClient;
