import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ProcessingStatus } from '@/types';

/** Minimal fake WebSocket: records listeners and lets tests fire events by hand. */
class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  readonly url: string;
  private readonly listeners: Record<string, ((event?: unknown) => void)[]> = {};

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  addEventListener(type: string, cb: (event?: unknown) => void): void {
    (this.listeners[type] ??= []).push(cb);
  }

  close(): void {
    this.emit('close');
  }

  emit(type: string, event?: unknown): void {
    this.listeners[type]?.forEach((cb) => cb(event));
  }
}

describe('WebSocketClient', () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal('WebSocket', FakeWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('connects to the processing-status path with the ws base URL', async () => {
    const { processingStatusClient } = await import('@/services/ws');
    const client = processingStatusClient('job-1');
    client.connect();
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.instances[0].url).toMatch(/\/processing-status\/job-1$/);
  });

  it('connects to the stack-status path', async () => {
    const { stackStatusClient } = await import('@/services/ws');
    const client = stackStatusClient('stack-1');
    client.connect();
    expect(FakeWebSocket.instances[0].url).toMatch(/\/stack-status\/stack-1$/);
  });

  it('delivers a camelCased status to listeners on message', async () => {
    const { processingStatusClient } = await import('@/services/ws');
    const client = processingStatusClient('job-1');
    client.connect();
    const listener = vi.fn();
    client.onStatusUpdate(listener);

    FakeWebSocket.instances[0].emit('message', {
      data: JSON.stringify({ job_id: 'job-1', status: 'processing', progress_percent: 42 }),
    });

    expect(listener).toHaveBeenCalledWith(
      expect.objectContaining({ jobId: 'job-1', status: 'processing', progressPercent: 42 }),
    );
  });

  it('ignores a malformed message frame instead of throwing', async () => {
    const { processingStatusClient } = await import('@/services/ws');
    const client = processingStatusClient('job-1');
    client.connect();
    const listener = vi.fn();
    client.onStatusUpdate(listener);

    expect(() => FakeWebSocket.instances[0].emit('message', { data: 'not json' })).not.toThrow();
    expect(listener).not.toHaveBeenCalled();
  });

  it('onStatusUpdate returns an unsubscribe function that stops further delivery', async () => {
    const { processingStatusClient } = await import('@/services/ws');
    const client = processingStatusClient('job-1');
    client.connect();
    const kept = vi.fn();
    const removed = vi.fn();
    client.onStatusUpdate(kept);
    const unsubscribe = client.onStatusUpdate(removed);

    unsubscribe();
    FakeWebSocket.instances[0].emit('message', {
      data: JSON.stringify({ job_id: 'job-1', status: 'processing', progress_percent: 1 } as Partial<ProcessingStatus>),
    });

    expect(kept).toHaveBeenCalledTimes(1);
    expect(removed).not.toHaveBeenCalled();
  });

  it('reconnects with exponential backoff (1s, 2s, ...) after an unexpected close, and "open" resets it', async () => {
    vi.useFakeTimers();
    const { processingStatusClient } = await import('@/services/ws');
    const client = processingStatusClient('job-1');
    client.connect();
    expect(FakeWebSocket.instances).toHaveLength(1);

    // First unexpected close -> reconnect scheduled after 1000ms.
    FakeWebSocket.instances[0].emit('close');
    vi.advanceTimersByTime(999);
    expect(FakeWebSocket.instances).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(FakeWebSocket.instances).toHaveLength(2);

    // Second unexpected close -> delay doubled to 2000ms.
    FakeWebSocket.instances[1].emit('close');
    vi.advanceTimersByTime(1999);
    expect(FakeWebSocket.instances).toHaveLength(2);
    vi.advanceTimersByTime(1);
    expect(FakeWebSocket.instances).toHaveLength(3);

    // A successful "open" resets the backoff back to 1000ms.
    FakeWebSocket.instances[2].emit('open');
    FakeWebSocket.instances[2].emit('close');
    vi.advanceTimersByTime(999);
    expect(FakeWebSocket.instances).toHaveLength(3);
    vi.advanceTimersByTime(1);
    expect(FakeWebSocket.instances).toHaveLength(4);
  });

  it('caps the reconnect delay at 30s', async () => {
    vi.useFakeTimers();
    const { processingStatusClient } = await import('@/services/ws');
    const client = processingStatusClient('job-1');
    client.connect();

    // 1s, 2s, 4s, 8s, 16s, then capped at 30s (not 32s).
    for (let i = 0; i < 5; i += 1) {
      const current = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
      current.emit('close');
      vi.runOnlyPendingTimers();
    }
    expect(FakeWebSocket.instances).toHaveLength(6);

    const last = FakeWebSocket.instances[5];
    last.emit('close');
    vi.advanceTimersByTime(29_999);
    expect(FakeWebSocket.instances).toHaveLength(6);
    vi.advanceTimersByTime(1);
    expect(FakeWebSocket.instances).toHaveLength(7);
  });

  it('disconnect() does not trigger a reconnect and clears listeners', async () => {
    vi.useFakeTimers();
    const { processingStatusClient } = await import('@/services/ws');
    const client = processingStatusClient('job-1');
    client.connect();
    const listener = vi.fn();
    client.onStatusUpdate(listener);

    client.disconnect();
    vi.advanceTimersByTime(60_000);
    expect(FakeWebSocket.instances).toHaveLength(1); // no reconnect scheduled

    // Listeners were cleared - a stray message after disconnect (defensive)
    // would not reach the old listener even if the socket were still around.
    FakeWebSocket.instances[0].emit('message', {
      data: JSON.stringify({ job_id: 'job-1', status: 'completed' }),
    });
    expect(listener).not.toHaveBeenCalled();
  });

  it('disconnect() before ever connecting is a no-op', async () => {
    const { processingStatusClient } = await import('@/services/ws');
    const client = processingStatusClient('job-1');
    expect(() => client.disconnect()).not.toThrow();
  });
});

describe('WS_URL resolution', () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal('WebSocket', FakeWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it('uses VITE_WS_URL directly when configured', async () => {
    vi.resetModules();
    vi.stubEnv('VITE_WS_URL', 'wss://configured.example/ws');
    const { processingStatusClient } = await import('@/services/ws');
    processingStatusClient('job-1').connect();
    expect(FakeWebSocket.instances[0].url).toBe('wss://configured.example/ws/processing-status/job-1');
  });

  it('derives ws:// from an http page origin when unconfigured', async () => {
    vi.resetModules();
    vi.stubEnv('VITE_WS_URL', '');
    vi.stubGlobal('location', { protocol: 'http:', host: 'app.example:3000' });
    const { processingStatusClient } = await import('@/services/ws');
    processingStatusClient('job-1').connect();
    expect(FakeWebSocket.instances[0].url).toBe('ws://app.example:3000/ws/processing-status/job-1');
  });

  it('derives wss:// from an https page origin when unconfigured', async () => {
    vi.resetModules();
    vi.stubEnv('VITE_WS_URL', '');
    vi.stubGlobal('location', { protocol: 'https:', host: 'app.example' });
    const { processingStatusClient } = await import('@/services/ws');
    processingStatusClient('job-1').connect();
    expect(FakeWebSocket.instances[0].url).toBe('wss://app.example/ws/processing-status/job-1');
  });

  it('falls back to a fixed default when window is unavailable (SSR-safe)', async () => {
    vi.resetModules();
    vi.stubEnv('VITE_WS_URL', '');
    vi.stubGlobal('window', undefined);
    const { processingStatusClient } = await import('@/services/ws');
    processingStatusClient('job-1').connect();
    expect(FakeWebSocket.instances[0].url).toBe('ws://localhost:3000/ws/processing-status/job-1');
  });
});
