import { expect, test, type Page } from '@playwright/test';

// The app behind a path prefix, the way a Home Assistant ingress serves it
// (e2e/ingress/fake-supervisor.mjs strips the prefix like the Supervisor does).
// Every request the browser makes - page, assets, API, images, WebSockets - must
// stay under the prefix: anything that escapes it would hit Home Assistant's own
// server instead of the app.
const ORIGIN = 'http://localhost:3112'; // INGRESS_PORT in playwright.config.ts
const PREFIX = '/api/hassio_ingress/e2e-token/';
const APP = `${ORIGIN}${PREFIX}`;
const SAMPLE = 'e2e/fixtures/sample.png';
const FRAMES = ['e2e/fixtures/sample.png', 'e2e/fixtures/frame-2.png', 'e2e/fixtures/frame-3.png'];
const ADMIN_PASSWORD = 'ingress e2e password';

interface Traffic {
  escaped: string[];
  failed: string[];
}

/** Record every request outside the prefix and every failed response. */
function watchTraffic(page: Page): Traffic {
  const traffic: Traffic = { escaped: [], failed: [] };
  const check = (url: string) => {
    if (url.startsWith('http') && !url.startsWith(APP)) {
      traffic.escaped.push(url);
    }
  };
  page.on('request', (request) => check(request.url()));
  page.on('websocket', (socket) => check(socket.url().replace(/^ws/, 'http')));
  page.on('response', (response) => {
    if (response.status() >= 400) {
      traffic.failed.push(`${response.status()} ${response.url()}`);
    }
  });
  return traffic;
}

test('the editor works end to end behind the ingress prefix', async ({ page }) => {
  const traffic = watchTraffic(page);

  await page.goto(APP);
  await page.locator('input[type=file]').setInputFiles(SAMPLE);
  const rail = page.locator('nav[aria-label="Editing workflow"]');
  await expect(rail).toBeVisible();
  await expect(page.locator('img[alt="Original"], img').first()).toBeVisible();

  await rail.getByRole('button', { name: 'Light' }).click();
  const processed = page.waitForResponse(
    (r) => r.url().startsWith(`${APP}api/process/`) && r.ok(),
  );
  await page.getByRole('slider', { name: 'Contrast' }).fill('1.8');
  await processed;

  await rail.getByRole('button', { name: 'Export' }).click();
  const [file] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Download' }).click(),
  ]);
  expect(file.suggestedFilename()).toBe('sample_myastroshine.jpg');

  expect(traffic.escaped).toEqual([]);
  expect(traffic.failed).toEqual([]);
});

test('stacking, its thumbnails and its progress socket stay behind the prefix', async ({ page }) => {
  test.slow();
  const traffic = watchTraffic(page);

  await page.goto(APP);
  await page.getByRole('button', { name: 'Multi-Image Stack' }).click();
  await page.locator('input[type=file]').first().setInputFiles(FRAMES);
  await page.getByRole('button', { name: /Upload 3 frames/ }).click();
  await expect(page.getByRole('checkbox')).toHaveCount(3);
  await expect(page.locator(`img[src^="${PREFIX}api/stack/"]`).first()).toBeVisible();

  const socket = page.waitForEvent('websocket');
  await page.getByRole('button', { name: /Stack 3 frames/ }).click();
  expect((await socket).url()).toContain(`${PREFIX}ws/stack-status/`);
  await expect(page.getByText('Frames stacked')).toBeVisible({ timeout: 45_000 });
  await expect(page.locator(`img[src^="${PREFIX}api/preview/"]`)).toBeVisible();

  expect(traffic.escaped).toEqual([]);
  expect(traffic.failed).toEqual([]);
});

test('the admin login works behind the prefix', async ({ page }) => {
  const traffic = watchTraffic(page);

  await page.goto(`${APP}#/settings`);
  const setup = page.getByRole('heading', { name: 'Create the admin password' });
  const login = page.getByRole('heading', { name: 'Administrator login' });
  await expect(setup.or(login)).toBeVisible();
  if (await setup.isVisible()) {
    await page.getByLabel('New password').fill(ADMIN_PASSWORD);
    await page.getByLabel('Confirm the password').fill(ADMIN_PASSWORD);
    await page.getByRole('button', { name: 'Create and log in' }).click();
  } else {
    await page.getByLabel('Admin password').fill(ADMIN_PASSWORD);
    await page.getByRole('button', { name: 'Log in' }).click();
  }

  await expect(page.getByLabel('Maximum upload size')).toBeVisible();
  await page.reload(); // the session cookie survives a reload behind the prefix
  await expect(page.getByLabel('Maximum upload size')).toBeVisible();

  expect(traffic.escaped).toEqual([]);
  expect(traffic.failed.filter((line) => !line.includes('/api/auth/'))).toEqual([]);
});
