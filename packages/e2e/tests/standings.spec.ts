import { test, expect } from '../fixtures/supabase-mock.fixture';
import {
  setupSupabaseMocks,
  mockTableData,
  mockTableList,
} from '../fixtures/supabase-mock.fixture';
import { mockUser } from '../fixtures/auth.fixture';
import { StandingsPage } from '../page-objects';

const NAV_TIMEOUT = { timeout: 15000 };
const LEAGUE_ID = 'standings-league-1111-2222-333333333333';

// ---------------------------------------------------------------------------
// Mock data: league
// ---------------------------------------------------------------------------
const leagueData = {
  name: 'Standings Cup League',
  current_round: 2,
};

// ---------------------------------------------------------------------------
// Mock data: 5 league members ranked by total_points descending
// ---------------------------------------------------------------------------
const membersData = [
  {
    id: 'member-001',
    user_id: 'user-alice-id',
    team_name: 'Ice Dominators',
    total_points: 62,
    users: { display_name: 'Alice' },
  },
  {
    id: 'member-002',
    user_id: mockUser.id, // current user — 2nd place
    team_name: 'Puck Dynasty',
    total_points: 55,
    users: { display_name: 'Test User' },
  },
  {
    id: 'member-003',
    user_id: 'user-charlie-id',
    team_name: 'Goal Getters',
    total_points: 48,
    users: { display_name: 'Charlie' },
  },
  {
    id: 'member-004',
    user_id: 'user-diana-id',
    team_name: 'Net Crushers',
    total_points: 31,
    users: { display_name: 'Diana' },
  },
  {
    id: 'member-005',
    user_id: 'user-evan-id',
    team_name: 'Blue Line Brigade',
    total_points: 19,
    users: { display_name: 'Evan' },
  },
];

// ---------------------------------------------------------------------------
// Setup helper
// ---------------------------------------------------------------------------
async function setupStandingsMocks(page: import('@playwright/test').Page) {
  await setupSupabaseMocks(page, {
    leagues: mockTableData([], leagueData),
    league_members: mockTableList(membersData),
  });
}

// ──────────────────────────────────────────────────────────────────────────────
// Standings Tests
// ──────────────────────────────────────────────────────────────────────────────
test.describe('Standings Page', () => {
  test('standings page shows all league members ranked by total points', async ({
    authenticatedPage,
  }) => {
    await setupStandingsMocks(authenticatedPage);
    const standings = new StandingsPage(authenticatedPage);
    await standings.goto(LEAGUE_ID);

    // Heading visible
    await expect(standings.heading).toBeVisible(NAV_TIMEOUT);

    // League name and round
    await expect(
      authenticatedPage.getByText('Standings Cup League')
    ).toBeVisible();
    await expect(authenticatedPage.getByText(/Round 2/)).toBeVisible();

    // All 5 members visible
    const rows = standings.getMemberRows();
    await expect(rows).toHaveCount(5);

    // Verify ranking order — first row should be Alice (62 pts)
    const firstRow = rows.nth(0);
    await expect(firstRow.getByText('Ice Dominators')).toBeVisible();
    await expect(firstRow.getByText('Alice')).toBeVisible();
    await expect(firstRow.getByText('62')).toBeVisible();

    // Last place — Evan (19 pts)
    const lastRow = rows.nth(4);
    await expect(lastRow.getByText('Blue Line Brigade')).toBeVisible();
    await expect(lastRow.getByText('Evan')).toBeVisible();
    await expect(lastRow.getByText('19')).toBeVisible();

    // Medal badges for top 3
    await expect(authenticatedPage.getByText('1st')).toBeVisible();
    await expect(authenticatedPage.getByText('2nd')).toBeVisible();
    await expect(authenticatedPage.getByText('3rd')).toBeVisible();
  });

  test.skip('points breakdown columns are displayed (player points, goalie points)', async () => {
    // StandingsPage currently shows only total_points — breakdown columns not implemented yet
  });

  test.skip('round-by-round point columns are shown', async () => {
    // StandingsPage currently shows only a single total_points column — round columns not implemented yet
  });

  test('current user row is visually highlighted', async ({
    authenticatedPage,
  }) => {
    await setupStandingsMocks(authenticatedPage);
    const standings = new StandingsPage(authenticatedPage);
    await standings.goto(LEAGUE_ID);

    await expect(standings.heading).toBeVisible(NAV_TIMEOUT);

    // Current user row has "You" badge
    const userRow = standings.getCurrentUserRow();
    await expect(userRow).toBeVisible();
    await expect(userRow.getByText('You')).toBeVisible();

    // Row shows current user's team and points
    await expect(userRow.getByText('Puck Dynasty')).toBeVisible();
    await expect(userRow.getByText('55')).toBeVisible();

    // 2nd place medal badge in the user's row
    await expect(userRow.getByText('2nd')).toBeVisible();
  });

  test.skip('CSV export button triggers download of standings data', async () => {
    // StandingsPage does not have a CSV export button yet
  });
});
