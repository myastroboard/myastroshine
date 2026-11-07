import { expect, test, type Page } from '@playwright/test';

const SAMPLE = 'e2e/fixtures/sample.png';

/** Upload the sample and wait for the editor (its workflow rail) to mount. */
async function openEditor(page: Page): Promise<void> {
  await page.goto('/');
  await page.locator('input[type=file]:not([multiple])').setInputFiles(SAMPLE);
  await expect(page.locator('nav[aria-label="Editing workflow"]')).toBeVisible();
}

/** Click a step in the workflow rail. */
async function openStep(page: Page, name: string): Promise<void> {
  // Anchored at the start so 'Stars' does not also match 'Separate stars'; not
  // exact, because a changed step's name ends with a 'changed from default' marker.
  const label = new RegExp(`^${name}\\b`);
  await page
    .locator('nav[aria-label="Editing workflow"]')
    .getByRole('button', { name: label })
    .click();
}

test('star removal splits the pipeline, then recombine brings the stars back', async ({ page }) => {
  await openEditor(page);
  await openStep(page, 'Separate stars');

  const processed = page.locator('img[alt="Processed"]');
  await expect(processed).toBeVisible();

  const remove = page.getByRole('slider', { name: 'Remove stars' });
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

  // The Separate stars rail step now carries the "changed from default" dot.
  await expect(
    page
      .locator('nav[aria-label="Editing workflow"]')
      .getByRole('button', { name: /^Separate stars\b/ }),
  ).toHaveAccessibleName(/changed from default/);

  // Bringing the stars back (the other half, in the Stars step) reprocesses again.
  await openStep(page, 'Stars');
  const recombine = page.getByRole('slider', { name: 'Bring stars back' });
  const beforeRecombine = await processed.getAttribute('src');
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/process/') && r.ok()),
    recombine.fill('100'),
  ]);
  await expect(processed).not.toHaveAttribute('src', beforeRecombine ?? '');
});
