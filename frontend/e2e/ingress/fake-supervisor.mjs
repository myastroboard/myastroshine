// A stand-in for the Home Assistant Supervisor's ingress proxy, for the
// "ingress" e2e project (e2e/ingress/ingress.spec.ts).
//
// The browser loads the app at http://localhost:3112/api/hassio_ingress/e2e-token/.
// Like the Supervisor, this strips that prefix and forwards to the app: /api and
// /ws go to the backend (WebSocket upgrades included), anything else is served
// from the production build in dist/ - the way the backend serves it in the
// image. A request that escapes the prefix gets a 404, which is exactly what it
// would get from Home Assistant: the spec fails on it.
//
// Usage: node e2e/ingress/fake-supervisor.mjs  (after `npm run build`)

import { createReadStream, existsSync, statSync } from 'node:fs';
import http from 'node:http';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const PORT = Number(process.env.INGRESS_PORT ?? 3112);
const BACKEND_HOST = '127.0.0.1';
const BACKEND_PORT = Number(process.env.BACKEND_PORT ?? 8012);
export const PREFIX = '/api/hassio_ingress/e2e-token';

const DIST = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../dist');
const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.json': 'application/json',
};

/** The path the app sees, or null when the request escaped the prefix. */
function stripPrefix(url) {
  if (url === PREFIX) {
    return '/';
  }
  return url.startsWith(`${PREFIX}/`) ? url.slice(PREFIX.length) : null;
}

/** The headers the Supervisor adds (see HA_APP_RETEX.md, "Ingress"): the app is
 * reached on its own host, the browser's host comes as X-Forwarded-Host, and HA
 * core's own hop (172.30.32.1) follows the browser's in X-Forwarded-For. The
 * backend trusts them because playwright.config.ts starts it as an HA app
 * (SUPERVISOR_TOKEN) with this proxy's address (INGRESS_PROXY_IP). */
function forwardedHeaders(req) {
  return {
    ...req.headers,
    host: `${BACKEND_HOST}:${BACKEND_PORT}`,
    'x-ingress-path': PREFIX,
    'x-forwarded-for': `${req.socket.remoteAddress ?? ''}, 172.30.32.1`,
    'x-remote-user-id': 'e2e-ha-user',
    'x-forwarded-host': req.headers.host ?? '',
    'x-forwarded-proto': 'http',
  };
}

function serveStatic(appPath, res) {
  const clean = decodeURIComponent(appPath.split('?')[0]);
  const file = path.join(DIST, clean === '/' ? 'index.html' : clean);
  if (!file.startsWith(DIST) || !existsSync(file) || !statSync(file).isFile()) {
    res.writeHead(404).end();
    return;
  }
  res.writeHead(200, { 'content-type': TYPES[path.extname(file)] ?? 'application/octet-stream' });
  createReadStream(file).pipe(res);
}

const server = http.createServer((req, res) => {
  const appPath = stripPrefix(req.url ?? '');
  if (appPath === null) {
    res.writeHead(404, { 'content-type': 'text/plain' }).end(`escaped the ingress prefix: ${req.url}`);
    return;
  }
  if (!appPath.startsWith('/api/') && !appPath.startsWith('/ws/')) {
    serveStatic(appPath, res);
    return;
  }
  const upstream = http.request(
    { host: BACKEND_HOST, port: BACKEND_PORT, method: req.method, path: appPath, headers: forwardedHeaders(req) },
    (backendRes) => {
      res.writeHead(backendRes.statusCode ?? 502, backendRes.headers);
      backendRes.pipe(res);
    },
  );
  upstream.on('error', () => res.writeHead(502).end());
  req.pipe(upstream);
});

server.on('upgrade', (req, socket, head) => {
  const appPath = stripPrefix(req.url ?? '');
  if (appPath === null || !appPath.startsWith('/ws/')) {
    socket.end('HTTP/1.1 404 Not Found\r\n\r\n');
    return;
  }
  const backend = net.connect(BACKEND_PORT, BACKEND_HOST, () => {
    const headers = Object.entries(forwardedHeaders(req))
      .map(([name, value]) => `${name}: ${value}`)
      .join('\r\n');
    backend.write(`GET ${appPath} HTTP/1.1\r\n${headers}\r\n\r\n`);
    backend.write(head);
    backend.pipe(socket);
    socket.pipe(backend);
  });
  backend.on('error', () => socket.destroy());
  socket.on('error', () => backend.destroy());
});

server.listen(PORT, () => {
  process.stdout.write(`fake supervisor on http://localhost:${PORT}${PREFIX}/\n`);
});
