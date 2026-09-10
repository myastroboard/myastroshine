import { expect, test, type Page } from '@playwright/test';

const SAMPLE = 'e2e/fixtures/sample.png';

/** Upload the sample and wait for the editor (its workflow rail) to mount. */
async function openEditor(page: Page): Promise<void> {
  await page.goto('/');
  await page.locator('input[type=file]').setInputFiles(SAMPLE);
  await expect(page.locator('nav[aria-label="Editing workflow"]')).toBeVisible();
}

/** Click a step in the workflow rail (Start / Framing / Light / ... / Export). */
async function openStep(page: Page, name: string): Promise<void> {
  await page.locator('nav[aria-label="Editing workflow"]').getByRole('button', { name }).click();
}

test('upload, adjust a slider, and download the result', async ({ page }) => {
  await openEditor(page);
  await openStep(page, 'Light');

  const processed = page.waitForResponse(
    (r) => r.url().includes('/api/process/') && r.request().method() === 'POST' && r.ok(),
  );
  await page.getByRole('slider', { name: 'Contrast' }).fill('2');
  await processed;

  await openStep(page, 'Export');
  const download = page.getByRole('button', { name: 'Download' });
  await expect(download).toBeVisible();

  // The filename field is seeded from the uploaded file plus a "_myastroshine" suffix.
  const filename = page.getByLabel('File name');
  await expect(filename).toHaveValue('sample_myastroshine');

  await filename.fill('my orion');
  const [file] = await Promise.all([page.waitForEvent('download'), download.click()]);
  expect(file.suggestedFilename()).toBe('my orion.jpg');
});

test('adjusting a slider refreshes the processed preview', async ({ page }) => {
  await openEditor(page);
  await openStep(page, 'Light');

  const processed = page.locator('img[alt="Processed"]');
  await expect(processed).toBeVisible();
  const before = await processed.getAttribute('src');

  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/process/') && r.ok()),
    page.getByRole('slider', { name: 'Contrast' }).fill('2.4'),
  ]);
  await expect(processed).not.toHaveAttribute('src', before ?? '');
  expect(await processed.getAttribute('src')).toContain('full=true');
  expect(await page.locator('img[alt="Original"]').getAttribute('src')).toContain('original=true');
});

test('a slider renders when released, not mid-drag', async ({ page }) => {
  await openEditor(page);
  await openStep(page, 'Light');

  let renders = 0;
  page.on('request', (r) => {
    if (r.url().includes('/api/process/') && r.method() === 'POST') renders += 1;
  });

  const slider = page.getByRole('slider', { name: 'Contrast' });
  const box = (await slider.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  for (const frac of [0.6, 0.75, 0.9]) {
    await page.mouse.move(box.x + box.width * frac, box.y + box.height / 2);
    await page.waitForTimeout(700); // a pause a time-based debounce would have fired on
  }
  expect(renders).toBe(0);

  await page.mouse.up();
  await page.waitForResponse((r) => r.url().includes('/api/process/') && r.ok());
  expect(renders).toBe(1);
});

test('the before/after divider drags without selecting content', async ({ page }) => {
  await openEditor(page);

  const frame = page.locator('img[alt="Processed"]');
  await expect(frame).toBeVisible();
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
  await openEditor(page);
  await openStep(page, 'Depth');

  await page.getByRole('button', { name: 'Open Depth Shift viewer' }).click();

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
  await openEditor(page);
  await openStep(page, 'Export');

  await page.getByRole('button', { name: 'Save as preset' }).click();

  const dialog = page.getByRole('heading', { name: 'Save as preset' });
  await expect(dialog).toBeVisible();

  const name = `E2E ${Date.now()}`;
  await page.getByPlaceholder('My nebula look').fill(name);
  await Promise.all([
    page.waitForResponse(
      (r) => r.url().endsWith('/api/presets') && r.request().method() === 'POST' && r.ok(),
    ),
    page.getByRole('button', { name: 'Save', exact: true }).click(),
  ]);
  await expect(dialog).toBeHidden();

  await openStep(page, 'Start');
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

test('framing crops and rotates on the preview', async ({ page }) => {
  await openEditor(page);
  await openStep(page, 'Framing');

  const apply = page.getByRole('button', { name: 'Apply framing' });
  await expect(apply).toBeVisible();

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
    apply.click(),
  ]);

  // committed: the Framing rail step now carries the "changed from default" dot
  await expect(
    page.locator('nav[aria-label="Editing workflow"]').getByRole('button', { name: 'Framing' }),
  ).toHaveAccessibleName(/changed from default/);

  // leaving Framing, the before/after split has both frames aligned again
  await openStep(page, 'Light');
  await expect(page.locator('img[alt="Original"]')).toHaveCount(1);
  await expect(page.locator('img[alt="Processed"]')).toBeVisible();
});

test('"New photo" confirms before discarding edits, then returns to upload', async ({ page }) => {
  await openEditor(page);

  // no edits yet -> leaves straight away
  await page.getByRole('button', { name: 'New photo' }).click();
  await expect(page.getByRole('button', { name: 'Choose a file' })).toBeVisible();

  // re-enter, make an edit (dirty client-side at once), and the exit is guarded
  await page.locator('input[type=file]').setInputFiles(SAMPLE);
  await openStep(page, 'Light');
  await page.getByRole('slider', { name: 'Contrast' }).fill('1.7');

  await page.getByRole('button', { name: 'New photo' }).click();
  const dialog = page.getByRole('dialog', { name: 'Discard your edits?' });
  await expect(dialog).toBeVisible();

  await dialog.getByRole('button', { name: 'Cancel' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole('slider', { name: 'Contrast' })).toHaveValue('1.7');

  await page.getByRole('button', { name: 'New photo' }).click();
  await dialog.getByRole('button', { name: 'Discard and continue' }).click();
  await expect(page.getByRole('button', { name: 'Choose a file' })).toBeVisible();
});

test('applying a preset moves the sliders and star reduction works', async ({ page }) => {
  await openEditor(page);

  await openStep(page, 'Light');
  const contrast = page.getByRole('slider', { name: 'Contrast' });
  await expect(contrast).toHaveValue('1');

  await openStep(page, 'Start');
  const nebula = page.getByRole('button', { name: 'Nebula', exact: true });
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/apply/') && r.ok()),
    nebula.click(),
  ]);
  await expect(nebula).toHaveAttribute('aria-pressed', 'true');

  await openStep(page, 'Light');
  await expect(contrast).not.toHaveValue('1'); // preset pushed its value into the slider

  await openStep(page, 'Stars');
  const stars = page.getByRole('slider', { name: 'Star reduction' });
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/process/') && r.ok()),
    stars.fill('60'),
  ]);
  await expect(stars).toHaveValue('60');

  // a manual edit deselects the preset
  await openStep(page, 'Start');
  await expect(nebula).toHaveAttribute('aria-pressed', 'false');
});
