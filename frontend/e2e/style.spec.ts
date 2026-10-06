import { expect, test, type Page } from '@playwright/test';

const SAMPLE = 'e2e/fixtures/sample.png';

async function openEditor(page: Page): Promise<void> {
  await page.goto('/');
  await page.locator('input[type=file]:not([multiple])').setInputFiles(SAMPLE);
  await expect(page.locator('nav[aria-label="Editing workflow"]')).toBeVisible();
}

async function openStep(page: Page, name: string): Promise<void> {
  await page.locator('nav[aria-label="Editing workflow"]').getByRole('button', { name }).click();
}

test('pick a finishing style from the gallery and export with or without it', async ({ page }) => {
  await openEditor(page);
  await openStep(page, 'Style');

  const gallery = page.getByRole('radiogroup', { name: 'Finishing styles' });
  await expect(gallery.getByRole('radio')).toHaveCount(4);
  // Every thumbnail is the user's own image, rendered by the server.
  for (const img of await gallery.locator('img').all()) {
    await expect(img).toHaveJSProperty('complete', true);
    expect(await img.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(0);
  }

  const processed = page.waitForResponse(
    (r) => r.url().includes('/api/process/') && r.request().method() === 'POST' && r.ok(),
  );
  await gallery.getByRole('radio', { name: 'Vivid' }).click();
  const body = (await processed).request().postDataJSON() as {
    parameters: { look: { look_id: string; amount: number } };
  };
  expect(body.parameters.look).toEqual({ look_id: 'vivid', amount: 60 });
  await expect(page.getByRole('slider', { name: 'Strength' })).toBeVisible();

  await openStep(page, 'Export');
  await expect(page.getByRole('radio', { name: 'With style (Vivid)' })).toHaveAttribute(
    'aria-checked',
    'true',
  );
  await page.getByRole('radio', { name: 'Without style' }).click();
  const [request] = await Promise.all([
    page.waitForRequest((r) => r.url().includes('/api/download/')),
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Download' }).click(),
  ]);
  expect(request.postDataJSON()).toMatchObject({ style: false });
});
