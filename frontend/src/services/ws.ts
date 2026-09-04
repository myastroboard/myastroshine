// WebSocket client for real-time job status.
// Reconnects with exponential backoff (1s, 2s, 4s, 8s, max 30s).

import type { ProcessingStatus } from '@/types';

import { keysToCamelCase } from './caseConvert';

/** Absolute ws:// base. `VITE_WS_URL` wins; otherwise `/ws` on the page origin. */
const WS_URL = ((): string => {
  const configured = import.meta.env.VITE_WS_URL;
  if (configured) {
    return configured;
  }
  if (typeof window === 'undefined') {
    return 'ws://localhost:3000/ws';
  }
  const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${scheme}//${window.location.host}/ws`;
})();

type StatusListener = (status: ProcessingStatus) => void;

export class WebSocketClient {
  private socket: WebSocket | null = null;
  private listeners = new Set<StatusListener>();
  private reconnectDelay = 1000;
  private readonly maxDelay = 30000;
  private closedByCaller = false;

  constructor(private readonly path: string) {}

  connect(): void {
    this.closedByCaller = false;
    this.socket = new WebSocket(`${WS_URL}${this.path}`);

    this.socket.addEventListener('message', (event) => {
      try {
        const status = keysToCamelCase<ProcessingStatus>(JSON.parse(event.data as string));
        this.listeners.forEach((listener) => listener(status));
      } catch {
        // Ignore malformed frames.
      }
    });

    this.socket.addEventListener('open', () => {
      this.reconnectDelay = 1000;
    });

    this.socket.addEventListener('close', () => {
      if (!this.closedByCaller) {
        setTimeout(() => this.connect(), this.reconnectDelay);
        this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxDelay);
      }
    });
  }

  onStatusUpdate(listener: StatusListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  disconnect(): void {
    this.closedByCaller = true;
    this.socket?.close();
    this.socket = null;
    this.listeners.clear();
  }
}

export function processingStatusClient(jobId: string): WebSocketClient {
  return new WebSocketClient(`/processing-status/${jobId}`);
}

export function stackStatusClient(jobId: string): WebSocketClient {
  return new WebSocketClient(`/stack-status/${jobId}`);
}
