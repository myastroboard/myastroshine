import { expect, test, type Page } from '@playwright/test';

const SAMPLE = 'e2e/fixtures/sample.png';

/** Upload the sample and wait for the editor (its workflow rail) to mount. */
async function openEditor(page: Page): Promise<void> {
  await page.goto('/');
  await page.locator('input[type=file]').setInputFiles(SAMPLE);
  await expect(page.locator('nav[aria-label="Editing workflow"]')).toBeVisible();
}

/** Click a step in the workflow rail. */
async function openStep(page: Page, name: string): Promise<void> {
  await page.locator('nav[aria-label="Editing workflow"]').getByRole('button', { name }).click();
}

test('star removal splits the pipeline, then recombine brings the stars back', async ({ page }) => {
  await openEditor(page);
  await openStep(page, 'Stars');

  const processed = page.locator('img[alt="Processed"]');
  await expect(processed).toBeVisible();

  const remove = page.getByRole('slider', { name: 'Remove stars' });
  const recombine = page.getByRole('slider', { name: 'Bring stars back' });
  await expect(remove).toHaveValue('0');

  // Raising Remove re-runs the pipeline down the starless branch.
  const beforeRemove = await processed.getAttribute('src');
  await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes('/api/process/') && r.request().method() === 'POST' && r.ok(),
    ),
    remove.fill('100'),
  ]);
  await expect(processed).not.toHaveAttribute('src', beforeRemove ?? '');

  // The Stars rail step now carries the "changed from default" dot.
  await expect(
    page.locator('nav[aria-label="Editing workflow"]').getByRole('button', { name: 'Stars' }),
  ).toHaveAccessibleName(/changed from default/);

  // Bringing the stars back triggers another reprocess.
  const beforeRecombine = await processed.getAttribute('src');
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/process/') && r.ok()),
    recombine.fill('100'),
  ]);
  await expect(processed).not.toHaveAttribute('src', beforeRecombine ?? '');
});
