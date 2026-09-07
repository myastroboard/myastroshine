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

const processed = (page: Page) =>
  page.waitForResponse((r) => r.url().includes('/api/process/') && r.ok());

test('captures milestones and restores an earlier one', async ({ page }) => {
  await openEditor(page);

  const original = page.getByRole('button', { name: 'Restore Original' });
  await expect(original).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('button', { name: 'Restore Milestone 1' })).toHaveCount(0);

  await openStep(page, 'Light');
  const contrast = page.getByRole('slider', { name: 'Contrast' });
  await Promise.all([processed(page), contrast.fill('2')]);

  await page.getByRole('button', { name: 'Save milestone' }).click();
  const milestone1 = page.getByRole('button', { name: 'Restore Milestone 1' });
  await expect(milestone1).toHaveAttribute('aria-pressed', 'true');
  await expect(original).toHaveAttribute('aria-pressed', 'false');

  // Push it further - milestone 1 no longer matches the current state.
  await Promise.all([processed(page), contrast.fill('2.8')]);
  await expect(milestone1).toHaveAttribute('aria-pressed', 'false');

  // Restore milestone 1: the slider snaps back and it is the active match again.
  await Promise.all([processed(page), milestone1.click()]);
  await expect(contrast).toHaveValue('2');
  await expect(milestone1).toHaveAttribute('aria-pressed', 'true');

  // Restore the original.
  await Promise.all([processed(page), original.click()]);
  await expect(contrast).toHaveValue('1');
  await expect(original).toHaveAttribute('aria-pressed', 'true');
});

test('a new photo clears the milestones', async ({ page }) => {
  await openEditor(page);

  await openStep(page, 'Light');
  await Promise.all([processed(page), page.getByRole('slider', { name: 'Contrast' }).fill('1.8')]);
  await page.getByRole('button', { name: 'Save milestone' }).click();
  await expect(page.getByRole('button', { name: 'Restore Milestone 1' })).toBeVisible();

  await page.getByRole('button', { name: 'New photo' }).click();
  const dialog = page.getByRole('dialog', { name: 'Discard your edits?' });
  await dialog.getByRole('button', { name: 'Discard and continue' }).click();

  await page.locator('input[type=file]').setInputFiles(SAMPLE);
  await expect(page.locator('nav[aria-label="Editing workflow"]')).toBeVisible();

  await expect(page.getByRole('button', { name: 'Restore Milestone 1' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Restore Original' })).toBeVisible();
});
