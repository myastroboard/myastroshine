import { describe, expect, it } from 'vitest';

import { appPath, pageDirectory } from '@/services/appUrl';

describe('pageDirectory', () => {
  it.each([
    ['/', '/'],
    ['/index.html', '/'],
    ['/api/hassio_ingress/abc123/', '/api/hassio_ingress/abc123/'],
    ['/api/hassio_ingress/abc123/index.html', '/api/hassio_ingress/abc123/'],
    ['', '/'],
  ])('%s -> %s', (pathname, expected) => {
    expect(pageDirectory(pathname)).toBe(expected);
  });

  it('reads the current page by default', () => {
    expect(pageDirectory()).toBe('/');
  });
});

describe('appPath', () => {
  it('joins a server path under the page directory, with or without a leading slash', () => {
    expect(appPath('api')).toBe('/api');
    expect(appPath('/ws', '/proxy/myastroshine/')).toBe('/proxy/myastroshine/ws');
    expect(appPath('api', '/api/hassio_ingress/abc123/')).toBe('/api/hassio_ingress/abc123/api');
  });
});
