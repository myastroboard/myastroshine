import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end tests. Boots the real backend (sync processing, throwaway SQLite +
 * storage under .e2e-tmp) and the Vite dev server, then drives Chromium.
 *
 * Run: `npm run test:e2e` (needs `npx playwright install chromium` once and the
 * backend dependencies importable, i.e. `pip install -r ../backend/requirements.txt`).
 */
const BACKEND_PORT = 8002;
const FRONTEND_PORT = 3000;

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
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command:
        'python -m uvicorn app.main:app ' +
        `--host 127.0.0.1 --port ${BACKEND_PORT}`,
      cwd: '../backend',
      port: BACKEND_PORT,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: {
        APP_ENV: 'development',
        PROCESSING_MODE: 'sync',
        DATABASE_URL: 'sqlite:///./.e2e-tmp/e2e.db',
        STORAGE_PATH: './.e2e-tmp/images',
        STACKING_TEMP_DIR: './.e2e-tmp/stacks',
        ASTRODEX_WEBHOOK_SECRET: 'e2e-secret',
      },
    },
    {
      command: 'npm run dev',
      port: FRONTEND_PORT,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
