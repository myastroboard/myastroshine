import { expect, test } from '@playwright/test';

const SAMPLE = 'e2e/fixtures/sample.png';

test('upload, adjust a slider, and download the result', async ({ page }) => {
  await page.goto('/');

  await page.locator('input[type=file]').setInputFiles(SAMPLE);

  const download = page.getByRole('button', { name: 'Download' });
  await expect(download).toBeVisible();

  const processed = page.waitForResponse(
    (r) => r.url().includes('/api/process/') && r.request().method() === 'POST' && r.ok(),
  );
  await page.getByLabel('Contrast').fill('2');
  await processed;

  const [file] = await Promise.all([
    page.waitForEvent('download'),
    download.click(),
  ]);
  expect(file.suggestedFilename()).toMatch(/^myastroshine_.*\.jpg$/);
});

test('save the current parameters as a preset', async ({ page }) => {
  await page.goto('/');
  await page.locator('input[type=file]').setInputFiles(SAMPLE);
  await expect(page.getByRole('button', { name: 'Download' })).toBeVisible();

  await page.getByRole('button', { name: 'Save as preset' }).click();

  const dialog = page.getByRole('heading', { name: 'Save as preset' });
  await expect(dialog).toBeVisible();

  const name = `E2E ${Date.now()}`;
  await page.getByPlaceholder('My nebula look').fill(name);
  await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/api/presets') && r.request().method() === 'POST' && r.ok()),
    page.getByRole('button', { name: 'Save', exact: true }).click(),
  ]);

  await expect(dialog).toBeHidden();
  await expect(page.getByRole('button', { name: new RegExp(name) })).toBeVisible();
});
