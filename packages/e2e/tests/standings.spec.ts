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

  test('points breakdown columns are displayed (player points, goalie points)', async ({
    authenticatedPage,
  }) => {
    const membersWithBreakdown = membersData.map((m) => ({
      ...m,
      player_points: Math.floor(m.total_points * 0.7),
      goalie_points: m.total_points - Math.floor(m.total_points * 0.7),
    }));

    await setupSupabaseMocks(authenticatedPage, {
      leagues: mockTableData([], leagueData),
      league_members: mockTableList(membersWithBreakdown),
    });

    const standings = new StandingsPage(authenticatedPage);
    await standings.goto(LEAGUE_ID);
    await expect(standings.heading).toBeVisible(NAV_TIMEOUT);

    // Breakdown column headers should be visible
    await expect(authenticatedPage.getByText('Player Pts')).toBeVisible();
    await expect(authenticatedPage.getByText('Goalie Pts')).toBeVisible();

    // First row (Alice) — player_points = 43, goalie_points = 19
    const firstRow = standings.getMemberRows().nth(0);
    await expect(firstRow.getByText('43')).toBeVisible();
    await expect(firstRow.getByText('19')).toBeVisible();
  });

  test('round-by-round point columns are shown', async ({
    authenticatedPage,
  }) => {
    const membersWithRounds = membersData.map((m) => ({
      ...m,
      round_points: { 1: Math.floor(m.total_points * 0.6), 2: m.total_points - Math.floor(m.total_points * 0.6) },
    }));

    await setupSupabaseMocks(authenticatedPage, {
      leagues: mockTableData([], leagueData),
      league_members: mockTableList(membersWithRounds),
    });

    const standings = new StandingsPage(authenticatedPage);
    await standings.goto(LEAGUE_ID);
    await expect(standings.heading).toBeVisible(NAV_TIMEOUT);

    // Round column headers
    await expect(authenticatedPage.getByText('R1')).toBeVisible();
    await expect(authenticatedPage.getByText('R2')).toBeVisible();

    // Alice round 1 = 37, round 2 = 25
    const firstRow = standings.getMemberRows().nth(0);
    await expect(firstRow.getByText('37')).toBeVisible();
    await expect(firstRow.getByText('25')).toBeVisible();
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

  test('CSV export button triggers download of standings data', async ({
    authenticatedPage,
  }) => {
    await setupStandingsMocks(authenticatedPage);
    const standings = new StandingsPage(authenticatedPage);
    await standings.goto(LEAGUE_ID);
    await expect(standings.heading).toBeVisible(NAV_TIMEOUT);

    // CSV export button should be visible
    const exportButton = authenticatedPage.getByRole('button', {
      name: /Export CSV/i,
    });
    await expect(exportButton).toBeVisible();

    // Set up download listener
    const downloadPromise = authenticatedPage.waitForEvent('download');
    await exportButton.click();
    const download = await downloadPromise;

    // Verify a file was downloaded with csv extension
    expect(download.suggestedFilename()).toMatch(/\.csv$/);
  });
});
