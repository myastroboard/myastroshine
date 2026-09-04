// The backend speaks snake_case on the wire (see docs/API.md); the frontend
// uses camelCase everywhere. These helpers convert at the API/WebSocket boundary
// so nothing else in the app has to think about it.

function camelToSnake(key: string): string {
  return key.replace(/[A-Z]/g, (c) => `_${c.toLowerCase()}`);
}

function snakeToCamel(key: string): string {
  return key.replace(/_([a-z0-9])/g, (_, c: string) => c.toUpperCase());
}

function convertKeys(value: unknown, keyFn: (key: string) => string): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => convertKeys(item, keyFn));
  }
  if (value !== null && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [key, val] of Object.entries(value as Record<string, unknown>)) {
      out[keyFn(key)] = convertKeys(val, keyFn);
    }
    return out;
  }
  return value;
}

/** Recursively rewrite object keys to snake_case (for request bodies). */
export function keysToSnakeCase<T = unknown>(value: unknown): T {
  return convertKeys(value, camelToSnake) as T;
}

/** Recursively rewrite object keys to camelCase (for responses / WS messages). */
export function keysToCamelCase<T = unknown>(value: unknown): T {
  return convertKeys(value, snakeToCamel) as T;
}
