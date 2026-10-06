import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ADMIN_LOGIN_REQUIRED,
  ApiError,
  apiClient,
  onAdminLoginRequired,
  resolveApiPath,
} from '@/services/api';
import { DEFAULT_PARAMETERS } from '@/types';
import type { AppSettings, CalibrationKind, ConfigExport, FocusPoint, StackSettings } from '@/types';

// --- fetch mocking helpers ---------------------------------------------------

function jsonResponse(status: number, body: unknown): Response {
  const ok = status >= 200 && status < 300;
  const text = JSON.stringify(body);
  return {
    ok,
    status,
    statusText: `Status ${status}`,
    text: () => Promise.resolve(text),
    json: () => Promise.resolve(body),
    blob: () => Promise.resolve(new Blob([text], { type: 'application/json' })),
  } as unknown as Response;
}

function textErrorResponse(status: number, text: string): Response {
  return {
    ok: false,
    status,
    statusText: `Status ${status}`,
    text: () => Promise.resolve(text),
    json: () => Promise.reject(new Error('not json')),
    blob: () => Promise.resolve(new Blob([text])),
  } as unknown as Response;
}

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function lastCall(): [string, RequestInit | undefined] {
  const call = fetchMock.mock.calls[fetchMock.mock.calls.length - 1] as [
    string,
    RequestInit | undefined,
  ];
  return call;
}

// --- request()/readError() plumbing, exercised through a simple GET --------

describe('request() success path', () => {
  it('performs a GET with no body and converts the response to camelCase', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { cors_origins: ['*'], rate_limit_enabled: true }));
    const result = await apiClient.getAppSettings();
    const [url, init] = lastCall();
    expect(url).toBe('/api/admin/app-settings');
    expect(init?.method).toBe('GET');
    expect((init?.headers as Record<string, string>)['Content-Type']).toBeUndefined();
    expect(result.corsOrigins).toEqual(['*']);
    expect(result.rateLimitEnabled).toBe(true);
  });

  it('performs a POST with a snake_cased JSON body', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { session_id: 's1', job_id: 'j1' }));
    await apiClient.processImage('s1', DEFAULT_PARAMETERS);
    const [url, init] = lastCall();
    expect(url).toBe('/api/process/s1');
    expect(init?.method).toBe('POST');
    expect((init?.headers as Record<string, string>)['Content-Type']).toBe('application/json');
    const body = JSON.parse(init?.body as string);
    expect(body.parameters.geometry.rotate_quarters).toBe(0);
    expect(body.parameters.curve_points).toEqual([]);
  });

  it('returns undefined for a 204 No Content response without parsing a body', async () => {
    const response = jsonResponse(204, undefined);
    // Make json() throw if called - a 204 must short-circuit before reaching it.
    (response as unknown as { json: () => Promise<never> }).json = () =>
      Promise.reject(new Error('should not parse a 204 body'));
    fetchMock.mockResolvedValueOnce(response);
    await expect(apiClient.clearLogs()).resolves.toBeUndefined();
  });
});

describe('request() error path (readError branches)', () => {
  it('uses the JSON body\'s "error" field when present', async () => {
    fetchMock.mockResolvedValueOnce(textErrorResponse(404, JSON.stringify({ error: 'Session not found' })));
    await expect(apiClient.getAppSettings()).rejects.toMatchObject({
      status: 404,
      message: 'Session not found',
    });
  });

  it('falls back to the raw JSON text when the body has no "error" field', async () => {
    const raw = JSON.stringify({ detail: 'nope' });
    fetchMock.mockResolvedValueOnce(textErrorResponse(400, raw));
    await expect(apiClient.getAppSettings()).rejects.toMatchObject({ status: 400, message: raw });
  });

  it('falls back to the raw text when the body is not JSON', async () => {
    fetchMock.mockResolvedValueOnce(textErrorResponse(500, 'internal error'));
    await expect(apiClient.getAppSettings()).rejects.toMatchObject({
      status: 500,
      message: 'internal error',
    });
  });

  it("falls back to statusText instead of showing a proxy's HTML error page", async () => {
    const page = '<html> <head><title>413 Payload Too Large</title></head></html>';
    fetchMock.mockResolvedValueOnce(textErrorResponse(413, page));
    await expect(apiClient.getAppSettings()).rejects.toMatchObject({
      status: 413,
      message: 'Status 413',
      code: undefined,
    });
  });

  it('falls back to statusText when the body is empty and not JSON', async () => {
    fetchMock.mockResolvedValueOnce(textErrorResponse(503, ''));
    await expect(apiClient.getAppSettings()).rejects.toMatchObject({
      status: 503,
      message: 'Status 503',
    });
  });

  it('rejects with an ApiError instance', async () => {
    fetchMock.mockResolvedValueOnce(textErrorResponse(400, 'bad'));
    try {
      await apiClient.getAppSettings();
      expect.unreachable();
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).name).toBe('ApiError');
    }
  });
});

// --- previewUrl (pure, sync) -------------------------------------------------

describe('previewUrl', () => {
  it('with no options, returns just the base preview path', () => {
    expect(apiClient.previewUrl('s1')).toBe('/api/preview/s1');
  });

  it('sets original=true alone', () => {
    expect(apiClient.previewUrl('s1', { original: true })).toBe('/api/preview/s1?original=true');
  });

  it('sets original and geometry together', () => {
    expect(apiClient.previewUrl('s1', { original: true, geometry: true })).toBe(
      '/api/preview/s1?original=true&geometry=true',
    );
  });

  it('ignores geometry when original is not set', () => {
    expect(apiClient.previewUrl('s1', { geometry: true })).toBe('/api/preview/s1');
  });

  it('sets full=true when original is absent', () => {
    expect(apiClient.previewUrl('s1', { full: true })).toBe('/api/preview/s1?full=true');
  });

  it('prefers original over full when both are set', () => {
    expect(apiClient.previewUrl('s1', { original: true, full: true })).toBe(
      '/api/preview/s1?original=true',
    );
  });

  it('appends a numeric cache-busting v param', () => {
    expect(apiClient.previewUrl('s1', { v: 42 })).toBe('/api/preview/s1?v=42');
  });

  it('appends a string v param alongside other options', () => {
    expect(apiClient.previewUrl('s1', { full: true, v: 'abc' })).toBe(
      '/api/preview/s1?full=true&v=abc',
    );
  });
});

// --- downloadImage / exportLogs (fetch + blob(), not through request()) -----

describe('downloadImage', () => {
  it('POSTs format/quality and resolves a Blob on success', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { ok: true }));
    const blob = await apiClient.downloadImage('s1');
    const [url, init] = lastCall();
    expect(url).toBe('/api/download/s1');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual({ format: 'jpeg', quality: 95, style: true });
    expect(blob).toBeInstanceOf(Blob);
  });

  it('accepts a custom format/quality', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { ok: true }));
    await apiClient.downloadImage('s1', 'png', 80);
    const [, init] = lastCall();
    expect(JSON.parse(init?.body as string)).toEqual({ format: 'png', quality: 80, style: true });
  });

  it('can ask for the edit without its "Style" look', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { ok: true }));
    await apiClient.downloadImage('s1', 'jpeg', 95, false);
    const [, init] = lastCall();
    expect(JSON.parse(init?.body as string)).toEqual({
      format: 'jpeg',
      quality: 95,
      style: false,
    });
  });
});

describe('getLookCatalog', () => {
  it('GETs the session look catalogue', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        scene: 'nightscape',
        groups: [{ scene: 'nightscape', looks: ['galactic_core'] }],
      }),
    );
    const catalog = await apiClient.getLookCatalog('s1');
    const [url] = lastCall();
    expect(url).toBe('/api/looks/s1');
    expect(catalog).toEqual({
      scene: 'nightscape',
      groups: [{ scene: 'nightscape', looks: ['galactic_core'] }],
    });
  });
});

describe('lookThumbnailUrl', () => {
  it('builds the plain thumbnail URL without a look', () => {
    expect(apiClient.lookThumbnailUrl('s1', null)).toBe('/api/looks/s1/thumbnail');
    expect(apiClient.lookThumbnailUrl('s1', null, { amount: 40, v: 3 })).toBe(
      '/api/looks/s1/thumbnail?v=3',
    );
  });

  it('adds the look, its amount and the cache-buster', () => {
    expect(apiClient.lookThumbnailUrl('s1', 'vivid', { amount: 40, v: 3 })).toBe(
      '/api/looks/s1/thumbnail?look=vivid&amount=40&v=3',
    );
    expect(apiClient.lookThumbnailUrl('s1', 'cinematic')).toBe(
      '/api/looks/s1/thumbnail?look=cinematic',
    );
  });

  it('throws an ApiError on failure', async () => {
    fetchMock.mockResolvedValueOnce(textErrorResponse(500, 'boom'));
    await expect(apiClient.downloadImage('s1')).rejects.toMatchObject({ status: 500 });
  });
});

describe('exportLogs', () => {
  it('resolves a Blob on success', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, 'log lines'));
    const blob = await apiClient.exportLogs();
    const [url] = lastCall();
    expect(url).toBe('/api/admin/logs/export');
    expect(blob).toBeInstanceOf(Blob);
  });

  it('throws an ApiError on failure', async () => {
    fetchMock.mockResolvedValueOnce(textErrorResponse(500, 'boom'));
    await expect(apiClient.exportLogs()).rejects.toMatchObject({ status: 500 });
  });
});

// --- handoff / astrodex -------------------------------------------------------

describe('astrodex handoff', () => {
  it('resumeAstrodexHandoff POSTs the token', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { session_id: 's1', astrodex_item_id: 'i1' }));
    const result = await apiClient.resumeAstrodexHandoff('tok');
    const [url, init] = lastCall();
    expect(url).toBe('/api/astrodex/handoff/resume');
    expect(JSON.parse(init?.body as string)).toEqual({ handoff: 'tok' });
    expect(result.sessionId).toBe('s1');
  });

  it('returnToAstrodex POSTs the session id', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { session_id: 's1', status: 'sent', astrodex_item_id: 'i1' }));
    const result = await apiClient.returnToAstrodex('s1');
    const [url, init] = lastCall();
    expect(url).toBe('/api/astrodex/handoff/return');
    expect(JSON.parse(init?.body as string)).toEqual({ session_id: 's1' });
    expect(result.status).toBe('sent');
  });
});

// --- settings / engine status / logs -----------------------------------------

describe('settings and logs', () => {
  it('saveAppSettings POSTs the full settings object', async () => {
    const settings = { corsOrigins: [], rateLimitEnabled: false } as unknown as AppSettings;
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { cors_origins: [] }));
    await apiClient.saveAppSettings(settings);
    const [url, init] = lastCall();
    expect(url).toBe('/api/admin/app-settings');
    expect(init?.method).toBe('POST');
  });

  it('getEngineStatus GETs the engine status endpoint', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        starnet2: { configured: false, found: false, version: null, known_good: false, detail: '' },
        deepsnr: { configured: false, found: false, version: null, known_good: false, detail: '' },
      }),
    );
    const result = await apiClient.getEngineStatus();
    expect(lastCall()[0]).toBe('/api/admin/engine-status');
    expect(result.starnet2.configured).toBe(false);
  });

  it('getLogs defaults to limit=300 with no level param', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { lines: [], returned: 0, filtered_level: null }));
    await apiClient.getLogs();
    expect(lastCall()[0]).toBe('/api/admin/logs?limit=300');
  });

  it('getLogs includes a level param when given', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { lines: [], returned: 0, filtered_level: 'error' }));
    await apiClient.getLogs(50, 'error');
    expect(lastCall()[0]).toBe('/api/admin/logs?limit=50&level=error');
  });

  it('getLogLevels GETs the log-level endpoint', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { file: 'info', console: 'warning' }));
    const result = await apiClient.getLogLevels();
    expect(lastCall()[0]).toBe('/api/admin/logs/level');
    expect(result.console).toBe('warning');
  });

  it('clearLogs POSTs to the clear endpoint', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(204, undefined));
    await apiClient.clearLogs();
    const [url, init] = lastCall();
    expect(url).toBe('/api/admin/logs/clear');
    expect(init?.method).toBe('POST');
  });
});

// --- jobs / disk usage --------------------------------------------------------

describe('jobs and disk usage', () => {
  it('getJobs defaults limit/offset and omits status', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { jobs: [], total: 0, limit: 50, offset: 0 }));
    await apiClient.getJobs();
    expect(lastCall()[0]).toBe('/api/admin/jobs?limit=50&offset=0');
  });

  it('getJobs includes status/limit/offset when given', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { jobs: [], total: 0, limit: 10, offset: 5 }));
    await apiClient.getJobs({ status: 'failed', limit: 10, offset: 5 });
    expect(lastCall()[0]).toBe('/api/admin/jobs?limit=10&offset=5&status=failed');
  });

  it('getDiskUsage GETs the disk-usage endpoint', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        total_bytes: 1,
        used_bytes: 1,
        free_bytes: 1,
        images_bytes: 1,
        stacks_bytes: 1,
        db_bytes: 1,
        logs_bytes: 1,
      }),
    );
    await apiClient.getDiskUsage();
    expect(lastCall()[0]).toBe('/api/admin/disk-usage');
  });
});

// --- config export/import -----------------------------------------------------

describe('config export/import', () => {
  it('exportConfig GETs the export endpoint', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { format_version: 1, app_version: '1.0', exported_at: 't', settings: {}, presets: [] }),
    );
    await apiClient.exportConfig();
    expect(lastCall()[0]).toBe('/api/admin/config-export');
  });

  it('importConfig POSTs the config bundle', async () => {
    const config = { formatVersion: 1, presets: [] } as unknown as ConfigExport;
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { presets_imported: 0, presets_skipped: [] }));
    const result = await apiClient.importConfig(config);
    expect(lastCall()[0]).toBe('/api/admin/config-import');
    expect(result.presetsSkipped).toEqual([]);
  });
});

// --- tokens --------------------------------------------------------------------

describe('webhook tokens', () => {
  it('listTokens GETs /tokens', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { tokens: [], total: 0 }));
    await apiClient.listTokens();
    expect(lastCall()[0]).toBe('/api/tokens');
  });

  it('createToken POSTs a name with no expiry', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        id: 't1',
        name: 'n',
        token_prefix: 'abc',
        created_at: 't',
        last_used_at: null,
        expires_at: null,
        revoked: false,
        token: 'secret',
        signing_secret: 'sig',
      }),
    );
    const result = await apiClient.createToken('n');
    const [, init] = lastCall();
    expect(JSON.parse(init?.body as string)).toEqual({ name: 'n' });
    expect(result.token).toBe('secret');
  });

  it('createToken POSTs a name with an expiry', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        id: 't1',
        name: 'n',
        token_prefix: 'abc',
        created_at: 't',
        last_used_at: null,
        expires_at: 't2',
        revoked: false,
        token: 'secret',
        signing_secret: 'sig',
      }),
    );
    await apiClient.createToken('n', 30);
    const [, init] = lastCall();
    expect(JSON.parse(init?.body as string)).toEqual({ name: 'n', expires_in_days: 30 });
  });

  it('revokeToken DELETEs the token', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(204, undefined));
    await apiClient.revokeToken('t1');
    const [url, init] = lastCall();
    expect(url).toBe('/api/tokens/t1');
    expect(init?.method).toBe('DELETE');
  });
});

// --- presets ---------------------------------------------------------------------

describe('presets', () => {
  it('listPresets GETs /presets', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { presets: [], total: 0 }));
    await apiClient.listPresets();
    expect(lastCall()[0]).toBe('/api/presets');
  });

  it('savePreset POSTs the preset input', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { preset_id: 'p1', name: 'n', created_at: 't' }));
    const result = await apiClient.savePreset({ name: 'n', parameters: DEFAULT_PARAMETERS });
    expect(lastCall()[0]).toBe('/api/presets');
    expect(result.presetId).toBe('p1');
  });

  it('deletePreset DELETEs the preset', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(204, undefined));
    await apiClient.deletePreset('p1');
    const [url, init] = lastCall();
    expect(url).toBe('/api/presets/p1');
    expect(init?.method).toBe('DELETE');
  });

  it('applyPreset POSTs to the apply route', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { session_id: 's1', job_id: 'j1', status: 'queued', preview_url: '', estimated_time_seconds: 0, ws_status_url: '' }),
    );
    await apiClient.applyPreset('p1', 's1');
    expect(lastCall()[0]).toBe('/api/presets/p1/apply/s1');
  });
});

// --- auto astro / depth shift / star mask --------------------------------------

describe('auto astro, depth shift, star mask', () => {
  it('applyAutoAstro POSTs to the auto-astro route', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        session_id: 's1',
        job_id: 'j1',
        status: 'queued',
        preview_url: '',
        estimated_time_seconds: 0,
        ws_status_url: '',
        parameters: DEFAULT_PARAMETERS,
      }),
    );
    await apiClient.applyAutoAstro('s1');
    expect(lastCall()[0]).toBe('/api/auto-astro/s1');
  });

  it('generateDepthShift uses the default numLayers/intensity and omits focusPoint', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        session_id: 's1',
        num_layers: 7,
        depth_map_url: '',
        depth_layers: [],
        statistics: {},
      }),
    );
    await apiClient.generateDepthShift('s1');
    const [url, init] = lastCall();
    expect(url).toBe('/api/depth-shift/s1');
    expect(JSON.parse(init?.body as string)).toEqual({ num_layers: 7, intensity: 50 });
  });

  it('generateDepthShift includes a focusPoint when given', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        session_id: 's1',
        num_layers: 3,
        depth_map_url: '',
        depth_layers: [],
        statistics: {},
      }),
    );
    const focusPoint: FocusPoint = { x: 0.5, y: 0.5 };
    await apiClient.generateDepthShift('s1', 3, 80, focusPoint);
    const [, init] = lastCall();
    expect(JSON.parse(init?.body as string)).toEqual({
      num_layers: 3,
      intensity: 80,
      focus_point: { x: 0.5, y: 0.5 },
    });
  });

  it('detectStars POSTs sensitivity/maxSize', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { session_id: 's1', source_count: 0, stars: [] }));
    await apiClient.detectStars('s1', 40, 20);
    const [url, init] = lastCall();
    expect(url).toBe('/api/star-mask/s1');
    expect(JSON.parse(init?.body as string)).toEqual({ sensitivity: 40, max_size: 20 });
  });
});

// --- stacking --------------------------------------------------------------------

const stackSettings: StackSettings = {
  registrationTransform: 'similarity',
  combinationMethod: 'average',
  rejectionAlgo: 'sigma',
  weighting: 'noise',
  cosmeticCorrection: true,
  qualityFilter: 'moderate',
  postProcess: true,
  drizzleFactor: 1,
};

describe('stacking', () => {
  it('initiateStack POSTs frameCount + settings', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { stack_id: 'st1', status: 'pending', frame_count: 10, received_frames: 0 }));
    const result = await apiClient.initiateStack(10, stackSettings);
    const [url, init] = lastCall();
    expect(url).toBe('/api/stack/initiate');
    const body = JSON.parse(init?.body as string);
    expect(body.frame_count).toBe(10);
    expect(result.stackId).toBe('st1');
  });

  it('uploadStackFrame POSTs a FormData with frame_index and file', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { frame_index: 2, received_frames: 3, frame_count: 10, status: 'ok' }));
    const file = new File(['data'], 'frame.fits');
    const result = await apiClient.uploadStackFrame('st1', 2, file);
    const [url, init] = lastCall();
    expect(url).toBe('/api/stack/st1/upload-frame');
    const form = init?.body as FormData;
    expect(form.get('frame_index')).toBe('2');
    expect(form.get('file')).toBe(file);
    expect(result.frameIndex).toBe(2);
  });

  it('uploadStackFrame throws an ApiError on failure', async () => {
    fetchMock.mockResolvedValueOnce(textErrorResponse(400, 'bad frame'));
    const file = new File(['data'], 'frame.fits');
    await expect(apiClient.uploadStackFrame('st1', 0, file)).rejects.toMatchObject({ status: 400 });
  });

  it('uploadStackFrames POSTs start_index and multiple files', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { stack_id: 'st1', status: 'receiving', frame_count: 10, received_frames: 2 }));
    const files = [new File(['a'], 'a.fits'), new File(['b'], 'b.fits')];
    await apiClient.uploadStackFrames('st1', 0, files);
    const [url, init] = lastCall();
    expect(url).toBe('/api/stack/st1/upload-frames');
    const form = init?.body as FormData;
    expect(form.get('start_index')).toBe('0');
    expect(form.getAll('files')).toHaveLength(2);
  });

  describe('uploadStackFrames with progress (XMLHttpRequest)', () => {
    class FakeXhr {
      static last: FakeXhr;
      upload: { onprogress: ((event: Partial<ProgressEvent>) => void) | null } = {
        onprogress: null,
      };
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      status = 0;
      statusText = '';
      responseText = '';
      method = '';
      url = '';
      body: unknown = null;
      constructor() {
        FakeXhr.last = this;
      }
      open(method: string, url: string) {
        this.method = method;
        this.url = url;
      }
      send(body: unknown) {
        this.body = body;
      }
    }

    beforeEach(() => {
      vi.stubGlobal('XMLHttpRequest', FakeXhr);
    });

    afterEach(() => {
      vi.unstubAllGlobals();
      vi.stubGlobal('fetch', fetchMock);
    });

    it('reports the bytes sent and resolves the camelCased session', async () => {
      const progress: [number, number][] = [];
      const pending = apiClient.uploadStackFrames('st1', 4, [new File(['a'], 'a.fits')], (s, t) =>
        progress.push([s, t]),
      );
      const xhr = FakeXhr.last;
      expect(xhr.method).toBe('POST');
      expect(xhr.url).toBe('/api/stack/st1/upload-frames');
      expect((xhr.body as FormData).get('start_index')).toBe('4');
      xhr.upload.onprogress?.({ lengthComputable: true, loaded: 30, total: 60 });
      xhr.upload.onprogress?.({ lengthComputable: false, loaded: 0, total: 0 });
      xhr.status = 202;
      xhr.responseText = JSON.stringify({ stack_id: 'st1', received_frames: 5 });
      xhr.onload?.();

      await expect(pending).resolves.toMatchObject({ stackId: 'st1', receivedFrames: 5 });
      expect(progress).toEqual([[30, 60]]);
    });

    it('turns an error answer into an ApiError', async () => {
      const pending = apiClient.uploadStackFrames('st1', 0, [], () => undefined);
      const xhr = FakeXhr.last;
      xhr.status = 413;
      xhr.statusText = 'Payload Too Large';
      xhr.responseText = JSON.stringify({ error: { code: 'PAYLOAD_TOO_LARGE', message: 'too big' } });
      xhr.onload?.();

      await expect(pending).rejects.toMatchObject({ status: 413 });
    });

    it('rejects on a network failure', async () => {
      const pending = apiClient.uploadStackFrames('st1', 0, [], () => undefined);
      FakeXhr.last.onerror?.();

      await expect(pending).rejects.toBeInstanceOf(TypeError);
    });
  });

  it('uploadStackFrames throws an ApiError on failure', async () => {
    fetchMock.mockResolvedValueOnce(textErrorResponse(500, 'boom'));
    await expect(apiClient.uploadStackFrames('st1', 0, [])).rejects.toMatchObject({ status: 500 });
  });

  it('uploadStackArchive POSTs a FormData with the archive file', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { stack_id: 'st1', status: 'receiving', frame_count: 10, received_frames: 10 }));
    const file = new File(['zip'], 'archive.zip');
    await apiClient.uploadStackArchive('st1', file);
    const [url, init] = lastCall();
    expect(url).toBe('/api/stack/st1/upload-archive');
    expect((init?.body as FormData).get('file')).toBe(file);
  });

  it('uploadStackArchive throws an ApiError on failure', async () => {
    fetchMock.mockResolvedValueOnce(textErrorResponse(400, 'bad archive'));
    const file = new File(['zip'], 'archive.zip');
    await expect(apiClient.uploadStackArchive('st1', file)).rejects.toMatchObject({ status: 400 });
  });

  it('excludeStackFrame POSTs the excluded flag', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { index: 1, thumb_url: '', excluded: true, quality: null }));
    await apiClient.excludeStackFrame('st1', 1, true);
    const [url, init] = lastCall();
    expect(url).toBe('/api/stack/st1/frame/1/exclude');
    expect(JSON.parse(init?.body as string)).toEqual({ excluded: true });
  });

  it('uploadCalibrationFrames POSTs a FormData of files for the given kind', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { frames: { dark: 1, flat: 0, bias: 0, dark_flat: 0 }, cosmetic_correction: false }),
    );
    const kind: CalibrationKind = 'dark';
    const files = [new File(['d'], 'dark1.fits')];
    await apiClient.uploadCalibrationFrames('st1', kind, files);
    const [url, init] = lastCall();
    expect(url).toBe('/api/stack/st1/calibration/dark/frames');
    expect((init?.body as FormData).getAll('files')).toHaveLength(1);
  });

  it('uploadCalibrationFrames throws an ApiError on failure', async () => {
    fetchMock.mockResolvedValueOnce(textErrorResponse(400, 'bad calibration'));
    await expect(apiClient.uploadCalibrationFrames('st1', 'flat', [])).rejects.toMatchObject({
      status: 400,
    });
  });

  it('clearCalibration DELETEs the calibration kind', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { frames: { dark: 0, flat: 0, bias: 0, dark_flat: 0 }, cosmetic_correction: false }));
    await apiClient.clearCalibration('st1', 'bias');
    const [url, init] = lastCall();
    expect(url).toBe('/api/stack/st1/calibration/bias');
    expect(init?.method).toBe('DELETE');
  });

  it('processStack POSTs with no overrides', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        stack_id: 'st1',
        status: 'processing',
        session_id: null,
        stacked_image_url: null,
        statistics: null,
        frames: [],
        calibration: null,
        error: null,
      }),
    );
    await apiClient.processStack('st1');
    const [url, init] = lastCall();
    expect(url).toBe('/api/stack/st1/process');
    // `overrides` is undefined -> request() must skip the json branch entirely
    // (no body, no Content-Type header).
    expect(init?.body).toBeUndefined();
    expect((init?.headers as Record<string, string>)['Content-Type']).toBeUndefined();
  });

  it('processStack POSTs with overrides', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        stack_id: 'st1',
        status: 'processing',
        session_id: null,
        stacked_image_url: null,
        statistics: null,
        frames: [],
        calibration: null,
        error: null,
      }),
    );
    await apiClient.processStack('st1', stackSettings);
    const [, init] = lastCall();
    const body = JSON.parse(init?.body as string);
    expect(body.combination_method).toBe('average');
  });

  it('getStack GETs the stack result', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        stack_id: 'st1',
        status: 'done',
        session_id: 's1',
        stacked_image_url: 'u',
        statistics: null,
        frames: [],
        calibration: null,
        error: null,
      }),
    );
    const result = await apiClient.getStack('st1');
    expect(lastCall()[0]).toBe('/api/stack/st1');
    expect(result.sessionId).toBe('s1');
  });

  it('getLatestWatchStack GETs /stack/latest and can resolve null', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, null));
    const result = await apiClient.getLatestWatchStack();
    expect(lastCall()[0]).toBe('/api/stack/latest');
    expect(result).toBeNull();
  });
});

// --- version / config / capture info ---------------------------------------------

describe('version, config, capture info', () => {
  it('checkForUpdates GETs the version-check endpoint', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        current_version: '1.0',
        latest_version: null,
        update_available: false,
        release_url: null,
        release_name: null,
        release_notes: null,
        published_at: null,
        error: null,
      }),
    );
    await apiClient.checkForUpdates();
    expect(lastCall()[0]).toBe('/api/version/check-updates');
  });

  it('getConfig GETs the public config endpoint', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        max_image_size_mb: 50,
        stacking_enabled: true,
        stacking_max_frames: 100,
        starless_engines: ['classic'],
        denoise_engines: ['classic'],
      }),
    );
    const result = await apiClient.getConfig();
    expect(lastCall()[0]).toBe('/api/config');
    expect(result.stackingEnabled).toBe(true);
  });

  it('getCaptureInfo GETs the session capture-info endpoint and can resolve null', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, null));
    const result = await apiClient.getCaptureInfo('s1');
    expect(lastCall()[0]).toBe('/api/session/s1/capture-info');
    expect(result).toBeNull();
  });
});

// --- uploadImage / uploadWithProgress (XMLHttpRequest based) ----------------------

class FakeXhrUpload {
  listeners: Record<string, ((event: unknown) => void)[]> = {};
  addEventListener(type: string, cb: (event: unknown) => void): void {
    (this.listeners[type] ??= []).push(cb);
  }
  emit(type: string, event?: unknown): void {
    this.listeners[type]?.forEach((cb) => cb(event));
  }
}

class FakeXhr {
  static instances: FakeXhr[] = [];
  method = '';
  url = '';
  status = 0;
  statusText = '';
  responseText = '';
  sentBody: unknown;
  upload = new FakeXhrUpload();
  private readonly listeners: Record<string, ((event?: unknown) => void)[]> = {};

  constructor() {
    FakeXhr.instances.push(this);
  }

  open(method: string, url: string): void {
    this.method = method;
    this.url = url;
  }

  addEventListener(type: string, cb: (event?: unknown) => void): void {
    (this.listeners[type] ??= []).push(cb);
  }

  send(body: unknown): void {
    this.sentBody = body;
  }

  emit(type: string, event?: unknown): void {
    this.listeners[type]?.forEach((cb) => cb(event));
  }
}

describe('uploadImage / uploadWithProgress', () => {
  beforeEach(() => {
    FakeXhr.instances = [];
    vi.stubGlobal('XMLHttpRequest', FakeXhr);
  });

  it('opens a POST to /upload with the file in a FormData body', async () => {
    const file = new File(['bytes'], 'photo.jpg');
    const promise = apiClient.uploadImage(file);
    const xhr = FakeXhr.instances[0];
    expect(xhr.method).toBe('POST');
    expect(xhr.url).toBe('/api/upload');
    expect((xhr.sentBody as FormData).get('file')).toBe(file);

    xhr.status = 200;
    xhr.responseText = JSON.stringify({ session_id: 's1', is_stack: false });
    xhr.emit('load');
    const result = await promise;
    expect(result.sessionId).toBe('s1');
    expect(result.isStack).toBe(false);
  });

  it('reports upload progress only when lengthComputable', async () => {
    const file = new File(['bytes'], 'photo.jpg');
    const onProgress = vi.fn();
    const promise = apiClient.uploadImage(file, onProgress);
    const xhr = FakeXhr.instances[0];

    xhr.upload.emit('progress', { lengthComputable: false, loaded: 10, total: 100 });
    expect(onProgress).not.toHaveBeenCalled();

    xhr.upload.emit('progress', { lengthComputable: true, loaded: 25, total: 100 });
    expect(onProgress).toHaveBeenCalledWith(0.25);

    xhr.status = 200;
    xhr.responseText = JSON.stringify({ session_id: 's1' });
    xhr.emit('load');
    await promise;
  });

  it('does not register a progress listener when onProgress is omitted', () => {
    const file = new File(['bytes'], 'photo.jpg');
    void apiClient.uploadImage(file);
    const xhr = FakeXhr.instances[0];
    expect(xhr.upload.listeners.progress ?? []).toHaveLength(0);
  });

  it('rejects with "Malformed server response" when a 2xx body is not valid JSON', async () => {
    const file = new File(['bytes'], 'photo.jpg');
    const promise = apiClient.uploadImage(file);
    const xhr = FakeXhr.instances[0];
    xhr.status = 200;
    xhr.responseText = 'not json';
    xhr.emit('load');
    await expect(promise).rejects.toMatchObject({ status: 200, message: 'Malformed server response' });
  });

  it('rejects using the JSON "error" field on a failure status', async () => {
    const file = new File(['bytes'], 'photo.jpg');
    const promise = apiClient.uploadImage(file);
    const xhr = FakeXhr.instances[0];
    xhr.status = 413;
    xhr.statusText = 'Payload Too Large';
    xhr.responseText = JSON.stringify({ error: 'File too large' });
    xhr.emit('load');
    await expect(promise).rejects.toMatchObject({ status: 413, message: 'File too large' });
  });

  it('rejects using the raw response text when a failure body is not JSON', async () => {
    const file = new File(['bytes'], 'photo.jpg');
    const promise = apiClient.uploadImage(file);
    const xhr = FakeXhr.instances[0];
    xhr.status = 500;
    xhr.statusText = 'Internal Server Error';
    xhr.responseText = 'plain text failure';
    xhr.emit('load');
    await expect(promise).rejects.toMatchObject({ status: 500, message: 'plain text failure' });
  });

  it('rejects using statusText when a failure body has no text at all', async () => {
    const file = new File(['bytes'], 'photo.jpg');
    const promise = apiClient.uploadImage(file);
    const xhr = FakeXhr.instances[0];
    xhr.status = 500;
    xhr.statusText = 'Internal Server Error';
    xhr.responseText = '';
    xhr.emit('load');
    await expect(promise).rejects.toMatchObject({ status: 500, message: 'Internal Server Error' });
  });

  it('rejects with a network error on the "error" event', async () => {
    const file = new File(['bytes'], 'photo.jpg');
    const promise = apiClient.uploadImage(file);
    FakeXhr.instances[0].emit('error');
    await expect(promise).rejects.toMatchObject({ status: 0, message: 'Network error during upload' });
  });

  it('rejects with a cancellation error on the "abort" event', async () => {
    const file = new File(['bytes'], 'photo.jpg');
    const promise = apiClient.uploadImage(file);
    FakeXhr.instances[0].emit('abort');
    await expect(promise).rejects.toMatchObject({ status: 0, message: 'Upload cancelled' });
  });
});

// --- admin authentication --------------------------------------------------

describe('admin auth', () => {
  it('getAuthStatus GETs the status and camelCases it', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { admin_enabled: true, configured: true, authenticated: false }),
    );
    await expect(apiClient.getAuthStatus()).resolves.toEqual({
      adminEnabled: true,
      configured: true,
      authenticated: false,
    });
    expect(lastCall()[0]).toBe('/api/auth/status');
  });

  it('setupAdmin and loginAdmin POST the password', async () => {
    fetchMock.mockResolvedValue(jsonResponse(204, null));
    await apiClient.setupAdmin('a long password');
    expect(lastCall()[0]).toBe('/api/auth/setup');
    expect(JSON.parse(lastCall()[1]?.body as string)).toEqual({ password: 'a long password' });

    await apiClient.loginAdmin('pw');
    expect(lastCall()[0]).toBe('/api/auth/login');
    expect(lastCall()[1]?.method).toBe('POST');
  });

  it('logoutAdmin POSTs with no body', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(204, null));
    await apiClient.logoutAdmin();
    expect(lastCall()[0]).toBe('/api/auth/logout');
    expect(lastCall()[1]?.body).toBeUndefined();
  });

  it('changeAdminPassword POSTs snake_cased current and new passwords', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(204, null));
    await apiClient.changeAdminPassword('old one', 'new one');
    expect(lastCall()[0]).toBe('/api/auth/password');
    expect(JSON.parse(lastCall()[1]?.body as string)).toEqual({
      current_password: 'old one',
      new_password: 'new one',
    });
  });

  it('listAdminSessions unwraps the sessions array', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        sessions: [{ id: 's1', client_ip: '10.0.0.2', user_agent: null, current: true }],
      }),
    );
    const sessions = await apiClient.listAdminSessions();
    expect(sessions[0]).toMatchObject({ id: 's1', clientIp: '10.0.0.2', current: true });
  });

  it('revokeAdminSession DELETEs the encoded id', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(204, null));
    await apiClient.revokeAdminSession('a/b');
    expect(lastCall()[0]).toBe('/api/auth/sessions/a%2Fb');
    expect(lastCall()[1]?.method).toBe('DELETE');
  });

  it('carries the error_code on ApiError', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(401, { error: 'Wrong password', error_code: 'INVALID_CREDENTIALS' }),
    );
    await expect(apiClient.loginAdmin('x')).rejects.toMatchObject({
      status: 401,
      message: 'Wrong password',
      code: 'INVALID_CREDENTIALS',
    });
  });

  it('notifies listeners on 401 ADMIN_LOGIN_REQUIRED, and only then', async () => {
    const listener = vi.fn();
    const unsubscribe = onAdminLoginRequired(listener);

    fetchMock.mockResolvedValueOnce(jsonResponse(401, { error: 'x', error_code: 'INVALID_CREDENTIALS' }));
    await expect(apiClient.loginAdmin('x')).rejects.toBeInstanceOf(ApiError);
    fetchMock.mockResolvedValueOnce(jsonResponse(403, { error: 'x', error_code: ADMIN_LOGIN_REQUIRED }));
    await expect(apiClient.getAppSettings()).rejects.toBeInstanceOf(ApiError);
    expect(listener).not.toHaveBeenCalled();

    fetchMock.mockResolvedValueOnce(jsonResponse(401, { error: 'x', error_code: ADMIN_LOGIN_REQUIRED }));
    await expect(apiClient.getAppSettings()).rejects.toBeInstanceOf(ApiError);
    expect(listener).toHaveBeenCalledTimes(1);

    unsubscribe();
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { error: 'x', error_code: ADMIN_LOGIN_REQUIRED }));
    await expect(apiClient.getAppSettings()).rejects.toBeInstanceOf(ApiError);
    expect(listener).toHaveBeenCalledTimes(1);
  });
});

// --- server-built URLs stay inside the app ----------------------------------

describe('server URLs in responses', () => {
  it('resolves /api paths against the API base and leaves other values alone', () => {
    expect(resolveApiPath('/api/preview/s1?full=true')).toBe('/api/preview/s1?full=true');
    expect(resolveApiPath('/api')).toBe('/api');
    expect(resolveApiPath('https://github.com/x')).toBe('https://github.com/x');
    expect(resolveApiPath('/apiary')).toBe('/apiary');
  });

  it('rewrites every *Url / *Urls field, however deep, and nothing else', async () => {
    vi.resetModules();
    vi.stubGlobal('location', { ...window.location, pathname: '/api/hassio_ingress/abc/' });
    const { apiClient: prefixed } = await import('@/services/api');
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        stacked_image_url: '/api/preview/s1?full=true',
        release_url: 'https://github.com/x',
        frames: [{ index: 0, thumb_url: '/api/stack/k/frame/0/thumb' }],
        layer_urls: ['/api/depth-shift/s1/layer_0', 7],
        statistics: null,
        note: '/api/not-a-url-field',
      }),
    );

    const result = (await prefixed.getStack('k')) as unknown as Record<string, unknown>;

    expect(result.stackedImageUrl).toBe('/api/hassio_ingress/abc/api/preview/s1?full=true');
    expect(result.releaseUrl).toBe('https://github.com/x');
    expect((result.frames as { thumbUrl: string }[])[0].thumbUrl).toBe(
      '/api/hassio_ingress/abc/api/stack/k/frame/0/thumb',
    );
    expect(result.layerUrls).toEqual(['/api/hassio_ingress/abc/api/depth-shift/s1/layer_0', 7]);
    expect(result.note).toBe('/api/not-a-url-field');
    expect(lastCall()[0]).toBe('/api/hassio_ingress/abc/api/stack/k');
    vi.resetModules();
  });
});

describe('engine packages', () => {
  it('stageEngine uploads the archive with progress to the stage route', async () => {
    class FakeXhr {
      static last: FakeXhr;
      status = 201;
      responseText = JSON.stringify({ staging_id: 'abc', license_text: 'L' });
      upload = { addEventListener: vi.fn() };
      private handlers: Record<string, () => void> = {};
      url = '';
      constructor() {
        FakeXhr.last = this;
      }
      open(_method: string, url: string) {
        this.url = url;
      }
      addEventListener(name: string, handler: () => void) {
        this.handlers[name] = handler;
      }
      send() {
        this.handlers.load();
      }
    }
    vi.stubGlobal('XMLHttpRequest', FakeXhr);

    const staged = await apiClient.stageEngine('starnet2', new File(['z'], 'a.zip'), vi.fn());

    expect(FakeXhr.last.url).toBe('/api/admin/engines/starnet2/stage');
    expect(staged).toMatchObject({ stagingId: 'abc', licenseText: 'L' });
  });

  it('installEngine posts the staging id with the licence accepted', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { configured: true, found: true }));
    await apiClient.installEngine('deepsnr', 'abc');
    expect(lastCall()[0]).toBe('/api/admin/engines/deepsnr/install');
    expect(JSON.parse(lastCall()[1]?.body as string)).toEqual({
      staging_id: 'abc',
      accept_license: true,
    });
  });

  it('discardStagedEngine and removeEngine DELETE their routes', async () => {
    fetchMock.mockResolvedValue(jsonResponse(204, null));
    await apiClient.discardStagedEngine('starnet2', 'a/b');
    expect(lastCall()[0]).toBe('/api/admin/engines/starnet2/stage/a%2Fb');
    await apiClient.removeEngine('starnet2');
    expect(lastCall()[0]).toBe('/api/admin/engines/starnet2');
    expect(lastCall()[1]?.method).toBe('DELETE');
  });
});

