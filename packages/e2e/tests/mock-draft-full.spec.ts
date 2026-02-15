import { test, expect } from '@playwright/test';

/**
 * Full mock draft end-to-end test.
 *
 * Requires the web app to be running with VITE_MOCK_MODE=true.
 * In mock mode, authentication and all data are handled automatically
 * by MockAuthProvider and MockDataProvider — no Supabase mocks needed.
 *
 * Flow: Dashboard → Create League (4 members) → League Dashboard →
 *       Draft Lobby → Start Draft → Complete all 44 picks → Draft Complete
 */
test.describe('Full Mock Draft', () => {
  test('completes a full 44-pick, 4-member, 11-round mock draft without Unknown', async ({
    page,
  }) => {
    test.setTimeout(180_000); // 3 minutes for full draft

    // ── Step 1: Dashboard (mock mode auto-authenticates) ──────────────
    await page.goto('/');
    await expect(
      page.getByRole('button', { name: /Create League/i }).first()
    ).toBeVisible({ timeout: 15_000 });

    // ── Step 2: Create a league with 4 members ───────────────────────
    await page
      .getByRole('button', { name: /Create League/i })
      .first()
      .click();
    await expect(page.getByLabel(/League Name/i)).toBeVisible({
      timeout: 10_000,
    });

    await page.getByLabel(/League Name/i).fill('E2E Draft League');
    await page.getByLabel(/Your Team Name/i).fill('E2E Team');

    // Set Max Participants to 4 (mock creates 3 bots + 1 human)
    const maxInput = page.getByLabel(/Max Participants/i);
    await maxInput.fill('');
    await maxInput.fill('4');

    await page.locator('button[type="submit"]').click();

    // ── Step 3: League Dashboard → Draft Lobby ───────────────────────
    await expect(page.getByText('E2E Draft League')).toBeVisible({
      timeout: 10_000,
    });
    await page.getByRole('button', { name: /Start Draft/i }).click();

    // ── Step 4: Start the draft ──────────────────────────────────────
    await expect(
      page.getByRole('button', { name: /Start Round 1 Draft/i })
    ).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: /Start Round 1 Draft/i }).click();

    // ── Step 5: Active draft page ────────────────────────────────────
    await expect(
      page.getByRole('heading', { name: /Draft Room/i })
    ).toBeVisible({ timeout: 15_000 });

    // ── Step 6: Complete all 11 human picks ──────────────────────────
    // Roster composition: 5F + 3D + 1G + 1 IR-F + 1 IR-D = 11 slots
    // Pick position filters in order so roster fills correctly.
    const positionFilters = [
      'Forwards', // F slot 1
      'Forwards', // F slot 2
      'Forwards', // F slot 3
      'Forwards', // F slot 4
      'Forwards', // F slot 5
      'Goalies', // G slot
      'Defense', // D slot 1
      'Defense', // D slot 2
      'Defense', // D slot 3
      'Forwards', // IR-F slot (auto-selected by smart pre-selection)
      'Defense', // IR-D slot (auto-selected by smart pre-selection)
    ];

    for (let pick = 0; pick < 11; pick++) {
      // Wait for "Your Turn!" badge (bots auto-pick in ~1-2s each)
      await expect(page.getByText('Your Turn!')).toBeVisible({
        timeout: 45_000,
      });

      // Verify no "Unknown" is shown for the current turn
      await expect(
        page.locator('text=Pick #').locator('..').locator('..')
      ).not.toContainText('Unknown');

      // Filter by the needed position
      await page.locator(`label:has-text("${positionFilters[pick]}")`).click();

      // Click first available "Draft" button
      const draftBtn = page.getByRole('button', { name: /^Draft$/i }).first();
      await expect(draftBtn).toBeVisible({ timeout: 5_000 });
      await draftBtn.click();

      // Confirm pick in the modal
      const confirmBtn = page.getByRole('button', { name: /Confirm Pick/i });
      await expect(confirmBtn).toBeVisible({ timeout: 5_000 });
      await confirmBtn.click();

      // Wait for modal to close before next iteration
      await expect(page.getByRole('dialog')).toBeHidden({ timeout: 5_000 });
    }

    // ── Step 7: Wait for draft completion ────────────────────────────
    // After the human's 11th pick, bots finish remaining picks (~1-2s each)
    await expect(
      page.getByRole('heading', { name: /Draft Complete/i })
    ).toBeVisible({ timeout: 60_000 });

    // All 44 picks accounted for
    await expect(page.getByText(/All 44 picks have been made/i)).toBeVisible();

    // ── Step 8: Verify no "Unknown" in the final draft history table ─
    const historyTable = page.getByRole('table');
    await expect(historyTable).toBeVisible();

    const rows = historyTable.getByRole('row');
    const rowCount = await rows.count();

    // At least 44 data rows + 1 header row
    expect(rowCount).toBeGreaterThanOrEqual(45);

    // Every data row (skip header at index 0) must not contain "Unknown"
    for (let i = 1; i < rowCount; i++) {
      await expect(rows.nth(i)).not.toContainText('Unknown');
    }
  });
});
