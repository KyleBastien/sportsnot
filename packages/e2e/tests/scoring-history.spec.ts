import { test } from '../fixtures/supabase-mock.fixture';

// ──────────────────────────────────────────────────────────────────────────────
// Scoring History Tests
//
// The scoring history page (/scoring/:leagueId) has not been implemented yet.
// These tests are skipped and will be enabled once the page is created.
// ──────────────────────────────────────────────────────────────────────────────
test.describe('Scoring History', () => {
  test.skip('scoring history page shows scoring events list', async () => {
    // Scoring history page not implemented yet — no route or component exists
  });

  test.skip('scoring events can be filtered by player, team, and date', async () => {
    // Scoring history page not implemented yet — no route or component exists
  });
});
