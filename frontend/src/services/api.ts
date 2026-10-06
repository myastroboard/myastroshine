// HTTP client for the MyAstroShine backend.
// One method per API endpoint; see docs/API.md for the contracts.
//
// The backend uses snake_case; request bodies and responses are converted at
// this boundary (see caseConvert.ts) so the rest of the app stays camelCase.

import type {
  AdminSession,
  AppSettings,
  AuthStatus,
  AutoAstroResult,
  CalibrationKind,
  CalibrationSummary,
  CaptureInfo,
  ConfigExport,
  ConfigImportResult,
  CreatedToken,
  DepthShiftResult,
  DiskUsage,
  EngineStatus,
  EngineStatusResponse,
  ExternalEngine,
  FocusPoint,
  HandoffResumeResponse,
  HandoffReturnResponse,
  JobListResult,
  LogLevel,
  LogLevels,
  LogTail,
  LookId,
  Preset,
  ProcessResponse,
  ProcessingParameters,
  PublicConfig,
  StackFrameInfo,
  StackResult,
  StackSession,
  StackSettings,
  StagedEngine,
  StarMaskResult,
  UploadFrameResult,
  UploadResponse,
  VersionCheckResult,
  WebhookToken,
} from '@/types';

import { appPath } from './appUrl';
import { keysToCamelCase, keysToSnakeCase } from './caseConvert';

/** The API base: `VITE_API_URL` when set (dev against another host), else `api`
 * under the page directory - `/api` at the root, `/<prefix>/api` behind a path
 * prefix (see appUrl.ts). */
const API_URL = import.meta.env.VITE_API_URL ?? appPath('api');

/**
 * A server-built path (`/api/preview/...`, as responses carry it) resolved
 * against {@link API_URL}, so it stays inside the app behind a path prefix. Any
 * other value (an absolute `https://` link, a relative path) is returned as is.
 */
export function resolveApiPath(path: string): string {
  return path === '/api' || path.startsWith('/api/') ? API_URL + path.slice('/api'.length) : path;
}

/** Rewrite every `...Url` / `...Urls` field of a response with {@link resolveApiPath}. */
function resolveServerUrls<T>(value: T): T {
  if (Array.isArray(value)) {
    return value.map((item: unknown) => resolveServerUrls(item)) as T;
  }
  if (value === null || typeof value !== 'object') {
    return value;
  }
  const out: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    if (/Urls?$/.test(key) && typeof item === 'string') {
      out[key] = resolveApiPath(item);
    } else if (/Urls$/.test(key) && Array.isArray(item)) {
      out[key] = item.map((entry: unknown) =>
        typeof entry === 'string' ? resolveApiPath(entry) : entry,
      );
    } else {
      out[key] = resolveServerUrls(item);
    }
  }
  return out as T;
}

/** A response body as the app uses it: camelCase keys, URLs inside the app. */
function fromServer<T>(body: unknown): T {
  return resolveServerUrls(keysToCamelCase<T>(body));
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    /** The envelope's `error_code` (docs/API.md), when the body carried one. */
    readonly code?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/** `error_code` of an admin route called without a live admin session. */
export const ADMIN_LOGIN_REQUIRED = 'ADMIN_LOGIN_REQUIRED';

type AdminLoginRequiredListener = () => void;
const adminLoginRequiredListeners = new Set<AdminLoginRequiredListener>();

/**
 * Be told when any admin call comes back `401 ADMIN_LOGIN_REQUIRED` (the session
 * expired, or was revoked from another browser), so the Settings page can fall
 * back to the login form. Returns the unsubscribe function.
 */
export function onAdminLoginRequired(listener: AdminLoginRequiredListener): () => void {
  adminLoginRequiredListeners.add(listener);
  return () => adminLoginRequiredListeners.delete(listener);
}

function parseError(status: number, text: string, fallback: string): ApiError {
  try {
    const body = JSON.parse(text) as { error?: string; error_code?: string };
    return new ApiError(status, body.error ?? text, body.error_code);
  } catch {
    // An HTML error page (a proxy's, not ours) is no message to show.
    const html = text.trimStart().startsWith('<');
    return new ApiError(status, html || !text ? fallback : text);
  }
}

async function readError(response: Response): Promise<ApiError> {
  const error = parseError(response.status, await response.text(), response.statusText);
  if (error.status === 401 && error.code === ADMIN_LOGIN_REQUIRED) {
    adminLoginRequiredListeners.forEach((listener) => listener());
  }
  return error;
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
          resolve(fromServer<T>(JSON.parse(xhr.responseText)));
        } catch {
          reject(new ApiError(xhr.status, 'Malformed server response'));
        }
        return;
      }
      reject(parseError(xhr.status, xhr.responseText, xhr.statusText));
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
  return fromServer<T>(await response.json());
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

  /**
   * The "Style" gallery thumbnail: the edit before its look, with `look` applied
   * at `amount` (`null`: the plain edit). Rendered from a small stored copy, so
   * it never re-runs the pipeline. `v` is the cache-buster, as for previews.
   */
  lookThumbnailUrl(
    sessionId: string,
    look: LookId | null,
    opts: { amount?: number; v?: number | string } = {},
  ): string {
    const params = new URLSearchParams();
    if (look !== null) {
      params.set('look', look);
      if (opts.amount !== undefined) {
        params.set('amount', String(opts.amount));
      }
    }
    if (opts.v !== undefined) {
      params.set('v', String(opts.v));
    }
    const query = params.toString();
    return `${API_URL}/looks/${sessionId}/thumbnail${query ? `?${query}` : ''}`;
  },

  /** `style`: with a "Style" look active, `false` downloads the edit without it. */
  async downloadImage(
    sessionId: string,
    format = 'jpeg',
    quality = 95,
    style = true,
  ): Promise<Blob> {
    const response = await fetch(`${API_URL}/download/${sessionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ format, quality, style }),
    });
    if (!response.ok) {
      throw await readError(response);
    }
    return response.blob();
  },

  /** Open an editing session from an Astrodex handoff token (the browser was
   * sent here by MyAstroBoard). The backend verifies the token and pulls the
   * source image itself. */
  resumeAstrodexHandoff(handoff: string): Promise<HandoffResumeResponse> {
    return request<HandoffResumeResponse>('/astrodex/handoff/resume', {
      method: 'POST',
      json: { handoff },
    });
  },

  /** Send the enhanced result back to Astrodex, where it is filed as a new
   * picture on the same object. */
  returnToAstrodex(sessionId: string): Promise<HandoffReturnResponse> {
    return request<HandoffReturnResponse>('/astrodex/handoff/return', {
      method: 'POST',
      json: { sessionId },
    });
  },

  // --- Runtime settings (Settings screen) ---
  getAuthStatus(): Promise<AuthStatus> {
    return request<AuthStatus>('/auth/status');
  },

  setupAdmin(password: string): Promise<void> {
    return request<void>('/auth/setup', { method: 'POST', json: { password } });
  },

  loginAdmin(password: string): Promise<void> {
    return request<void>('/auth/login', { method: 'POST', json: { password } });
  },

  logoutAdmin(): Promise<void> {
    return request<void>('/auth/logout', { method: 'POST' });
  },

  changeAdminPassword(currentPassword: string, newPassword: string): Promise<void> {
    return request<void>('/auth/password', {
      method: 'POST',
      json: { currentPassword, newPassword },
    });
  },

  async listAdminSessions(): Promise<AdminSession[]> {
    return (await request<{ sessions: AdminSession[] }>('/auth/sessions')).sessions;
  },

  revokeAdminSession(sessionId: string): Promise<void> {
    return request<void>(`/auth/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
  },

  getAppSettings(): Promise<AppSettings> {
    return request<AppSettings>('/admin/app-settings');
  },

  saveAppSettings(settings: AppSettings): Promise<AppSettings> {
    return request<AppSettings>('/admin/app-settings', { method: 'POST', json: settings });
  },

  /** Probe the configured StarNet2 / DeepSNR paths (Settings -> engine status line). */
  getEngineStatus(): Promise<EngineStatusResponse> {
    return request<EngineStatusResponse>('/admin/engine-status');
  },

  /** Upload an engine package (the CLI archive from starnetastro.com); the server
   * unpacks and checks it and answers with its licence text. */
  stageEngine(
    engine: ExternalEngine,
    archive: File,
    onProgress?: (fraction: number) => void,
  ): Promise<StagedEngine> {
    const form = new FormData();
    form.append('file', archive);
    return uploadWithProgress<StagedEngine>(`/admin/engines/${engine}/stage`, form, onProgress);
  },

  installEngine(engine: ExternalEngine, stagingId: string): Promise<EngineStatus> {
    return request<EngineStatus>(`/admin/engines/${engine}/install`, {
      method: 'POST',
      json: { stagingId, acceptLicense: true },
    });
  },

  discardStagedEngine(engine: ExternalEngine, stagingId: string): Promise<void> {
    return request<void>(`/admin/engines/${engine}/stage/${encodeURIComponent(stagingId)}`, {
      method: 'DELETE',
    });
  },

  removeEngine(engine: ExternalEngine): Promise<void> {
    return request<void>(`/admin/engines/${engine}`, { method: 'DELETE' });
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

  // --- Job history / disk usage (Settings -> Operations) ---
  getJobs(options: { status?: string; limit?: number; offset?: number } = {}): Promise<JobListResult> {
    const params = new URLSearchParams({
      limit: String(options.limit ?? 50),
      offset: String(options.offset ?? 0),
    });
    if (options.status) {
      params.set('status', options.status);
    }
    return request<JobListResult>(`/admin/jobs?${params.toString()}`);
  },

  getDiskUsage(): Promise<DiskUsage> {
    return request<DiskUsage>('/admin/disk-usage');
  },

  // --- Backup / restore: settings + user presets (Settings -> Advanced) ---
  exportConfig(): Promise<ConfigExport> {
    return request<ConfigExport>('/admin/config-export');
  },

  importConfig(config: ConfigExport): Promise<ConfigImportResult> {
    return request<ConfigImportResult>('/admin/config-import', { method: 'POST', json: config });
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
    return fromServer<UploadFrameResult>(await response.json());
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
    return fromServer<StackSession>(await response.json());
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
    return fromServer<StackSession>(await response.json());
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
    return fromServer<CalibrationSummary>(await response.json());
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

  /** The current folder-watch stack, or null when watch ingest is off / empty. */
  getLatestWatchStack(): Promise<StackResult | null> {
    return request<StackResult | null>('/stack/latest');
  },

  // --- Update check ---
  checkForUpdates(): Promise<VersionCheckResult> {
    return request<VersionCheckResult>('/version/check-updates');
  },

  /** Public runtime limits (upload size cap, stacking limits). */
  getConfig(): Promise<PublicConfig> {
    return request<PublicConfig>('/config');
  },

  /** The session's capture info (object, telescope, filter, frame count,
   * exposure) read off its source FITS header(s), or `null` if it has none. */
  getCaptureInfo(sessionId: string): Promise<CaptureInfo | null> {
    return request<CaptureInfo | null>(`/session/${sessionId}/capture-info`);
  },
};

export type ApiClient = typeof apiClient;
