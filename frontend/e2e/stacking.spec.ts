import { expect, test } from '@playwright/test';

const FRAMES = ['e2e/fixtures/sample.png', 'e2e/fixtures/frame-2.png', 'e2e/fixtures/frame-3.png'];

test('collect, upload, review and stack three frames, then enhance the composite', async ({
  page,
}) => {
  test.slow(); // registration + integration on real frames

  await page.goto('/');
  await page.getByRole('button', { name: 'Multi-Image Stack' }).click();

  await page.locator('input[type=file]').first().setInputFiles(FRAMES);

  await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes('/api/stack/') && r.url().includes('/upload-frames') && r.ok(),
    ),
    page.getByRole('button', { name: /Upload 3 frames/ }).click(),
  ]);

  // Review grid: three frame thumbnails, each with an exclude checkbox.
  await expect(page.getByRole('checkbox')).toHaveCount(3);

  await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes('/api/stack/') && r.url().includes('/process') && r.ok(),
    ),
    page.getByRole('button', { name: /Stack 3 frames/ }).click(),
  ]);

  await expect(page.getByText('Frames stacked')).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText('SNR improvement')).toBeVisible();

  await page.getByRole('button', { name: 'Enhance composite' }).click();

  // Handoff: back to the single-image editor on the composite session, opened on
  // the composite-only "Stack" step with the linear post-stack controls.
  const rail = page.locator('nav[aria-label="Editing workflow"]');
  await expect(rail).toBeVisible();
  await expect(rail.getByRole('button', { name: 'Stack' })).toBeVisible();
  await expect(page.getByRole('slider', { name: 'Stretch' })).toBeVisible();

  await rail.getByRole('button', { name: 'Light' }).click();
  await expect(page.getByRole('slider', { name: 'Contrast' })).toBeVisible();
});
