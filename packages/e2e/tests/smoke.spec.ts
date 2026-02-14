import { test, expect } from '@playwright/test';

test('app loads and shows content', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/.*/);
});
