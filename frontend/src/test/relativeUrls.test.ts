import { readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

// The app must work under a path prefix (a reverse proxy, a Home Assistant
// ingress), so no source file may hard-code a URL from the server root: it
// would escape the prefix. Server paths go through appPath() / API_URL
// (services/appUrl.ts, services/api.ts). The browser walk behind a fake
// ingress proxy (e2e/ingress) catches what a scan cannot; this catches the rest
// in milliseconds.
const SRC = path.resolve(import.meta.dirname, '..');

/** A root-absolute URL in a string literal or a JSX / CSS attribute. */
const ROOT_ABSOLUTE = [
  /['"`]\/(api|ws|assets|static)\b/,
  /\b(src|href|action)=["']\/(?!\/)/,
  /url\(\s*['"]?\/(?!\/)/,
];

/** The few lines that legitimately name a root path, each with its reason. */
const ALLOWED: Record<string, RegExp[]> = {
  // resolveApiPath() recognises the server's "/api/..." paths to rewrite them.
  'services/api.ts': [/path === '\/api' \|\| path.startsWith\('\/api\/'\)/],
};

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) {
      return name === 'test' ? [] : sourceFiles(full);
    }
    return /\.(ts|tsx|css)$/.test(name) && !/\.test\.tsx?$/.test(name) ? [full] : [];
  });
}

function isComment(line: string): boolean {
  return /^\s*(\/\/|\*|\/\*)/.test(line);
}

describe('no root-absolute URLs in the app source', () => {
  it('finds none outside the allow-list', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles(SRC)) {
      const relative = path.relative(SRC, file).replaceAll('\\', '/');
      const allowed = ALLOWED[relative] ?? [];
      readFileSync(file, 'utf-8')
        .split('\n')
        .forEach((line, index) => {
          if (isComment(line) || allowed.some((pattern) => pattern.test(line))) {
            return;
          }
          if (ROOT_ABSOLUTE.some((pattern) => pattern.test(line))) {
            offenders.push(`${relative}:${index + 1}: ${line.trim()}`);
          }
        });
    }

    expect(offenders).toEqual([]);
  });

  it('flags the patterns it is meant to flag', () => {
    const samples = [
      "fetch('/api/upload')",
      'new WebSocket(`/ws/x`)',
      '<img src="/logo.png" />',
      "background: url('/assets/bg.png')",
    ];
    for (const sample of samples) {
      expect(ROOT_ABSOLUTE.some((pattern) => pattern.test(sample)), sample).toBe(true);
    }
    expect(ROOT_ABSOLUTE.some((pattern) => pattern.test('href="https://github.com"'))).toBe(false);
    expect(ROOT_ABSOLUTE.some((pattern) => pattern.test("appPath('api')"))).toBe(false);
  });
});
