import path from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { configDefaults, defineConfig } from 'vitest/config';

// Where the dev server proxies /api and /ws. Local dev hits the host; the Docker
// dev stack sets this to the api service on the compose network.
const PROXY_TARGET = process.env.VITE_PROXY_TARGET ?? 'http://localhost:8002';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, 'src'),
    },
  },
  server: {
    port: 3000,
    host: true,
    // Bind-mounted source in Docker (esp. on Windows/macOS) needs polling for HMR.
    watch: process.env.VITE_USE_POLLING ? { usePolling: true } : undefined,
    proxy: {
      '/api': { target: PROXY_TARGET, changeOrigin: true },
      '/ws': { target: PROXY_TARGET, ws: true, changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
    // Playwright specs under e2e/ are run by `npm run test:e2e`, not vitest.
    exclude: [...configDefaults.exclude, 'e2e/**'],
  },
});
