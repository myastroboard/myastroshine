// Fail the build if the production bundle points at the server root.
//
// The app must work under a path prefix (a reverse proxy, a Home Assistant
// ingress): index.html and the stylesheets may only reference assets relatively
// (vite.config.ts `base: './'`). A root-absolute "/assets/..." or url(/...) would
// escape the prefix and 404.
//
// Usage: node scripts/check-dist-urls.mjs   (after `npm run build`; `npm run check:dist`)

import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const DIST = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../dist');
const PATTERNS = [
  /\b(?:src|href)=["']\/(?!\/)/g, // <script src="/...">, <link href="/...">
  /url\(\s*['"]?\/(?!\/)/g, // CSS url(/...)
];

const files = [
  path.join(DIST, 'index.html'),
  ...readdirSync(path.join(DIST, 'assets'))
    .filter((name) => name.endsWith('.css'))
    .map((name) => path.join(DIST, 'assets', name)),
];

const offenders = [];
for (const file of files) {
  const text = readFileSync(file, 'utf-8');
  for (const pattern of PATTERNS) {
    for (const match of text.matchAll(pattern)) {
      const at = match.index ?? 0;
      offenders.push(`${path.relative(DIST, file)}: ...${text.slice(Math.max(0, at - 20), at + 40)}...`);
    }
  }
}

if (offenders.length > 0) {
  process.stderr.write(`Root-absolute URLs in the build:\n${offenders.join('\n')}\n`);
  process.exit(1);
}
process.stdout.write(`dist URLs are relative (${files.length} files checked)\n`);
