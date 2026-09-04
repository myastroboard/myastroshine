import { expect, test } from '@playwright/test';

const FRAMES = ['e2e/fixtures/sample.png', 'e2e/fixtures/frame-2.png', 'e2e/fixtures/frame-3.png'];

test('stack three frames and enhance the composite', async ({ page }) => {
  test.slow(); // registration + combination on real frames

  await page.goto('/');
  await page.getByRole('button', { name: 'Multi-Image Stack' }).click();

  await page.locator('input[type=file]').setInputFiles(FRAMES);
  await expect(page.getByText('Frame 3:')).toBeVisible();

  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/stack/') && r.url().includes('/process') && r.ok()),
    page.getByRole('button', { name: /Stack 3 frames/ }).click(),
  ]);

  await expect(page.getByText('Frames stacked')).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText('SNR improvement')).toBeVisible();

  await page.getByRole('button', { name: 'Enhance composite' }).click();

  // Handoff: back to the single-image editor on the composite session.
  await expect(page.getByRole('button', { name: 'Download' })).toBeVisible();
  await expect(page.getByLabel('Contrast')).toBeVisible();
});
