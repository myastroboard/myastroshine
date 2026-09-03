// HTTP client for the MyAstroShine backend.
// One method per API endpoint; see docs/API.md for the contracts.

import type {
  Preset,
  ProcessResponse,
  ProcessingParameters,
  StackResult,
  StackSettings,
  UploadResponse,
  WebhookResponse,
} from '@/types';

const API_URL = import.meta.env.VITE_API_URL ?? '/api';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

export const apiClient = {
  async uploadImage(file: File): Promise<UploadResponse> {
    const form = new FormData();
    form.append('file', file);
    const response = await fetch(`${API_URL}/upload`, { method: 'POST', body: form });
    if (!response.ok) {
      throw new Error(`Upload failed: ${response.status}`);
    }
    return response.json() as Promise<UploadResponse>;
  },

  processImage(sessionId: string, parameters: ProcessingParameters): Promise<ProcessResponse> {
    return request<ProcessResponse>(`/process/${sessionId}`, {
      method: 'POST',
      body: JSON.stringify({ parameters }),
    });
  },

  previewUrl(sessionId: string, full = false): string {
    return `${API_URL}/preview/${sessionId}${full ? '?full=true' : ''}`;
  },

  async downloadImage(sessionId: string, format = 'jpeg', quality = 95): Promise<Blob> {
    const response = await fetch(`${API_URL}/download/${sessionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ format, quality }),
    });
    if (!response.ok) {
      throw new Error(`Download failed: ${response.status}`);
    }
    return response.blob();
  },

  sendToAstroDex(
    sessionId: string,
    astrodexImageId: string,
    parametersUsed: ProcessingParameters,
    callbackUrl: string,
  ): Promise<WebhookResponse> {
    return request<WebhookResponse>('/send-to-astrodex', {
      method: 'POST',
      body: JSON.stringify({
        session_id: sessionId,
        astrodex_image_id: astrodexImageId,
        parameters_used: parametersUsed,
        astrodex_callback_url: callbackUrl,
      }),
    });
  },

  listPresets(): Promise<{ presets: Preset[]; total: number }> {
    return request('/presets');
  },

  savePreset(preset: Omit<Preset, 'presetId' | 'author' | 'isFavorite'>): Promise<Preset> {
    return request<Preset>('/presets', { method: 'POST', body: JSON.stringify(preset) });
  },

  // --- Stacking (v1.1+) ---
  initiateStack(frameCount: number, settings: StackSettings): Promise<{ stackSessionId: string }> {
    return request('/stack/initiate', {
      method: 'POST',
      body: JSON.stringify({ frame_count: frameCount, ...settings }),
    });
  },

  getStack(stackId: string): Promise<StackResult> {
    return request<StackResult>(`/stack/${stackId}`);
  },
};

export type ApiClient = typeof apiClient;
