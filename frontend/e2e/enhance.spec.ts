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

test('adjusting a slider refreshes the processed preview', async ({ page }) => {
  await page.goto('/');
  await page.locator('input[type=file]').setInputFiles(SAMPLE);
  await expect(page.getByRole('button', { name: 'Download' })).toBeVisible();

  const processed = page.locator('img[alt="Processed"]');
  const before = await processed.getAttribute('src');

  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/process/') && r.ok()),
    page.getByLabel('Contrast').fill('2.4'),
  ]);
  await expect(processed).not.toHaveAttribute('src', before ?? '');
  expect(await processed.getAttribute('src')).toContain('full=true');
  expect(await page.locator('img[alt="Original"]').getAttribute('src')).toContain('original=true');
});

test('the before/after divider drags without selecting content', async ({ page }) => {
  await page.goto('/');
  await page.locator('input[type=file]').setInputFiles(SAMPLE);
  await expect(page.getByRole('button', { name: 'Download' })).toBeVisible();

  const frame = page.locator('img[alt="Processed"]');
  const box = (await frame.boundingBox())!;
  const clip = () =>
    page.locator('img[alt="Original"]').evaluate((el) => getComputedStyle(el).clipPath);
  const before = await clip();

  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.2, box.y + box.height * 0.5, { steps: 8 });
  await page.mouse.up();

  expect(await clip()).not.toBe(before);
  expect(await page.evaluate(() => String(window.getSelection()))).toBe('');
});

test('opens the depth shift viewer', async ({ page }) => {
  await page.goto('/');
  await page.locator('input[type=file]').setInputFiles(SAMPLE);
  await expect(page.getByRole('button', { name: 'Download' })).toBeVisible();

  await page.getByRole('button', { name: /depth shift/i }).click();

  const dialog = page.getByRole('dialog', { name: 'Depth shift viewer' });
  await expect(dialog).toBeVisible({ timeout: 20_000 });

  // The parallax layer PNGs actually load (would be 0 on a 4xx/5xx).
  const layer = dialog.getByRole('img').first();
  await expect
    .poll(() => layer.evaluate((el: HTMLImageElement) => el.naturalWidth), { timeout: 10_000 })
    .toBeGreaterThan(0);

  await dialog.getByLabel('Depth shift intensity').fill('80');
  await page.getByRole('button', { name: 'Close' }).click();
  await expect(dialog).toBeHidden();
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
  const chip = page.getByRole('button', { name, exact: true });
  await expect(chip).toBeVisible();

  // Built-ins have no delete affordance; the user preset does.
  await expect(page.getByRole('button', { name: 'Delete preset Nebula' })).toHaveCount(0);
  await chip.hover();
  await page.getByRole('button', { name: `Delete preset ${name}` }).click();
  await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes('/api/presets/') && r.request().method() === 'DELETE',
    ),
    page.getByRole('button', { name: `Confirm delete preset ${name}` }).click(),
  ]);
  await expect(chip).toHaveCount(0);
});

test('crop and rotate applies a new framing', async ({ page }) => {
  await page.goto('/');
  await page.locator('input[type=file]').setInputFiles(SAMPLE);
  await expect(page.getByRole('button', { name: 'Download' })).toBeVisible();

  await page.getByRole('button', { name: 'Crop & rotate' }).click();
  const done = page.getByRole('button', { name: 'Done' });
  await expect(done).toBeVisible();

  await page.getByLabel('Straighten').fill('12');

  // drag the crop frame's SE corner inward and check it actually resizes
  const frame = page.locator('.cursor-move');
  const box = (await frame.boundingBox())!;
  await page.mouse.move(box.x + box.width - 12, box.y + box.height - 12);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.55, box.y + box.height * 0.55, { steps: 12 });
  await page.mouse.up();
  const resized = (await frame.boundingBox())!;
  expect(resized.width).toBeLessThan(box.width - 20);
  expect(resized.height).toBeLessThan(box.height - 20);

  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/process/') && r.ok()),
    done.click(),
  ]);
  await expect(done).toBeHidden();
  // the before/after split still works after a crop: "before" is now the
  // original with the same geometry applied, so the two frames stay aligned
  await expect(page.locator('img[alt="Original"]')).toHaveCount(1);
  await expect(page.getByRole('button', { name: 'Crop & rotate' })).toHaveClass(/btn-primary/);
});

test('applying a preset moves the sliders and star reduction works', async ({ page }) => {
  await page.goto('/');
  await page.locator('input[type=file]').setInputFiles(SAMPLE);
  await expect(page.getByRole('button', { name: 'Download' })).toBeVisible();

  const contrast = page.getByLabel('Contrast');
  await expect(contrast).toHaveValue('1');

  const nebula = page.getByRole('button', { name: 'Nebula', exact: true });
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/apply/') && r.ok()),
    nebula.click(),
  ]);
  await expect(contrast).not.toHaveValue('1'); // preset pushed its value into the slider
  await expect(nebula).toHaveAttribute('aria-pressed', 'true');

  const stars = page.getByLabel('Star reduction');
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/process/') && r.ok()),
    stars.fill('60'),
  ]);
  await expect(stars).toHaveValue('60');
  // a manual edit deselects the preset
  await expect(nebula).toHaveAttribute('aria-pressed', 'false');
});
