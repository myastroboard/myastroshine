import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end tests. Boots the real backend (throwaway data tree under .e2e-tmp)
 * and the Vite dev server, then drives Chromium. The `ingress` project also
 * builds the app and serves it behind a Home Assistant style path prefix
 * (e2e/ingress/fake-supervisor.mjs) to prove no URL escapes the prefix.
 *
 * Run: `npm run test:e2e` (needs `npx playwright install chromium` once and the
 * backend dependencies importable, i.e. `pip install -r ../backend/requirements.txt`).
 */
// Ports of their own, never the dev stack's (8002 / 3000), and no server reuse:
// reusing whatever already listens there once ran these specs - and wrote their
// admin password - against a developer's running stack. A busy port now fails
// the run instead.
const BACKEND_PORT = 8012;
const FRONTEND_PORT = 3012;
const INGRESS_PORT = 3112;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['list']] : [['list']],
  timeout: 60_000,
  use: {
    baseURL: `http://localhost:${FRONTEND_PORT}`,
    trace: 'on-first-retry',
    // The app auto-detects the browser language; pin it so the specs' English
    // selectors hold regardless of the runner's locale.
    locale: 'en-US',
  },
  projects: [
    {
      name: 'chromium',
      testIgnore: 'ingress/**',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'ingress',
      testMatch: 'ingress/**/*.spec.ts',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command:
        // --no-proxy-headers like the image (app/serve.py): uvicorn's own
        // X-Forwarded-For handling would rewrite the peer before the ingress
        // middleware checks it is the Supervisor.
        'python -m uvicorn app.main:app --no-proxy-headers ' +
        `--host 127.0.0.1 --port ${BACKEND_PORT}`,
      cwd: '../backend',
      port: BACKEND_PORT,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        APP_ENV: 'development',
        DATA_DIR: './.e2e-tmp',
        // Run as a Home Assistant app whose Supervisor is the fake one on
        // loopback (e2e/ingress/fake-supervisor.mjs), so the ingress project
        // exercises the trusted-proxy path: client IP, prefix-scoped cookie.
        SUPERVISOR_TOKEN: 'e2e',
        INGRESS_PROXY_IP: '127.0.0.1',
      },
    },
    {
      command: `npm run dev -- --port ${FRONTEND_PORT} --strictPort`,
      port: FRONTEND_PORT,
      env: { VITE_PROXY_TARGET: `http://127.0.0.1:${BACKEND_PORT}` },
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: 'npm run build && node e2e/ingress/fake-supervisor.mjs',
      port: INGRESS_PORT,
      reuseExistingServer: false,
      timeout: 120_000,
      env: { INGRESS_PORT: String(INGRESS_PORT), BACKEND_PORT: String(BACKEND_PORT) },
    },
  ],
});
