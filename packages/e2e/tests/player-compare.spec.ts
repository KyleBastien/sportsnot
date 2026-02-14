import { test, expect } from '../fixtures/supabase-mock.fixture';
import { setupSupabaseMocks, mockTableList } from '../fixtures/supabase-mock.fixture';
import { mockUser } from '../fixtures/auth.fixture';

const NAV_TIMEOUT = { timeout: 15000 };
const LEAGUE_ID = 'compare-league-1111-2222-333333333333';
const MEMBER_ID = 'member-current-user-0001';
const OTHER_MEMBER_ID = 'member-other-user-0002';
const OTHER_USER_ID = '99999999-8888-7777-6666-555555555555';

// ---------------------------------------------------------------------------
// Mock data: league + members
// ---------------------------------------------------------------------------
const leagueData = {
  id: LEAGUE_ID,
  name: 'Compare Test League',
  commissioner_id: mockUser.id,
  invite_code: 'COMP01',
  max_participants: 4,
  status: 'active',
  current_round: 1,
  created_at: '2026-01-15T00:00:00.000Z',
  updated_at: '2026-02-14T00:00:00.000Z',
  league_members: [
    {
      id: MEMBER_ID,
      user_id: mockUser.id,
      team_name: 'My Team',
      total_points: 0,
      users: { display_name: 'Test User' },
    },
    {
      id: OTHER_MEMBER_ID,
      user_id: OTHER_USER_ID,
      team_name: 'Opponent Team',
      total_points: 0,
      users: { display_name: 'Other Player' },
    },
  ],
};

const membersListData = [
  {
    id: MEMBER_ID,
    user_id: mockUser.id,
    team_name: 'My Team',
    total_points: 0,
    users: { display_name: 'Test User' },
  },
  {
    id: OTHER_MEMBER_ID,
    user_id: OTHER_USER_ID,
    team_name: 'Opponent Team',
    total_points: 0,
    users: { display_name: 'Other Player' },
  },
];

// ---------------------------------------------------------------------------
// Mock data: draft (active, current user's turn)
// ---------------------------------------------------------------------------
function buildDraft() {
  return {
    id: 'draft-0001',
    league_id: LEAGUE_ID,
    round: 1,
    status: 'active',
    current_pick: 1,
    draft_order: [mockUser.id, OTHER_USER_ID],
    started_at: '2026-02-14T12:00:00.000Z',
    draft_picks: [] as unknown[],
  };
}

// ---------------------------------------------------------------------------
// Mock data: players
// ---------------------------------------------------------------------------
const mockPlayers = [
  { player_id: 8478402, nhl_season: '20252026', playoff_round: 1, player_name: 'Connor McDavid', team_abbreviation: 'EDM', position: 'F', goals: 8, assists: 12, games_played: 7, is_injured: false, last_updated: '2026-02-14T00:00:00Z' },
  { player_id: 8479318, nhl_season: '20252026', playoff_round: 1, player_name: 'Auston Matthews', team_abbreviation: 'TOR', position: 'F', goals: 6, assists: 5, games_played: 7, is_injured: false, last_updated: '2026-02-14T00:00:00Z' },
  { player_id: 8471675, nhl_season: '20252026', playoff_round: 1, player_name: 'Sidney Crosby', team_abbreviation: 'PIT', position: 'F', goals: 5, assists: 8, games_played: 6, is_injured: false, last_updated: '2026-02-14T00:00:00Z' },
  { player_id: 8477934, nhl_season: '20252026', playoff_round: 1, player_name: 'Leon Draisaitl', team_abbreviation: 'EDM', position: 'F', goals: 7, assists: 6, games_played: 7, is_injured: false, last_updated: '2026-02-14T00:00:00Z' },
  { player_id: 8479339, nhl_season: '20252026', playoff_round: 1, player_name: 'Mitch Marner', team_abbreviation: 'TOR', position: 'F', goals: 3, assists: 10, games_played: 7, is_injured: false, last_updated: '2026-02-14T00:00:00Z' },
  { player_id: 8480069, nhl_season: '20252026', playoff_round: 1, player_name: 'Cale Makar', team_abbreviation: 'COL', position: 'D', goals: 4, assists: 8, games_played: 6, is_injured: false, last_updated: '2026-02-14T00:00:00Z' },
];

const mockTeams = [
  { team_id: 22, nhl_season: '20252026', playoff_round: 1, team_name: 'Edmonton Oilers', team_abbreviation: 'EDM', wins: 4, shutouts: 1, is_eliminated: false, last_updated: '2026-02-14T00:00:00Z' },
];

// ---------------------------------------------------------------------------
// Route handler helpers
// ---------------------------------------------------------------------------
function leagueHandler() {
  return async (route: import('@playwright/test').Route) => {
    const request = route.request();
    const accept = request.headers()['accept'] ?? '';
    if (request.method() === 'GET' && accept.includes('vnd.pgrst.object+json')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(leagueData) });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  };
}

function draftHandler() {
  const draft = buildDraft();
  return async (route: import('@playwright/test').Route) => {
    const request = route.request();
    const accept = request.headers()['accept'] ?? '';
    if (request.method() === 'GET' && accept.includes('vnd.pgrst.object+json')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(draft) });
    }
    if (request.method() === 'GET') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([draft]) });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(draft) });
  };
}

// ---------------------------------------------------------------------------
// Setup helper
// ---------------------------------------------------------------------------
async function setupCompareMocks(page: import('@playwright/test').Page) {
  await setupSupabaseMocks(page, {
    leagues: leagueHandler(),
    league_members: mockTableList(membersListData),
    drafts: draftHandler(),
    draft_picks: mockTableList([]),
    player_stats_cache: mockTableList(mockPlayers),
    team_stats_cache: mockTableList(mockTeams),
    rosters: mockTableList([]),
  });
}

// ──────────────────────────────────────────────────────────────────────────────
// Player Compare Tests
// ──────────────────────────────────────────────────────────────────────────────
test.describe('Player Comparison', () => {
  test('adding a player to compare tray shows the compare bar', async ({
    authenticatedPage,
  }) => {
    await setupCompareMocks(authenticatedPage);
    await authenticatedPage.goto(`/draft/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /Draft Room/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Compare tray should not be visible initially
    await expect(authenticatedPage.getByTestId('compare-tray')).not.toBeVisible();

    // Click Compare button on McDavid's row
    const row = authenticatedPage.getByRole('row').filter({ hasText: 'Connor McDavid' });
    await row.getByRole('button', { name: /Compare/i }).click();

    // Compare tray should now appear
    const tray = authenticatedPage.getByTestId('compare-tray');
    await expect(tray).toBeVisible();
    await expect(tray.getByText(/Compare \(1\)/i)).toBeVisible();
    await expect(tray.getByText('Connor McDavid (EDM)')).toBeVisible();
  });

  test('up to 4 players can be compared side-by-side', async ({
    authenticatedPage,
  }) => {
    await setupCompareMocks(authenticatedPage);
    await authenticatedPage.goto(`/draft/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /Draft Room/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Add 4 players to compare
    const playerNames = ['Connor McDavid', 'Auston Matthews', 'Sidney Crosby', 'Leon Draisaitl'];
    for (const name of playerNames) {
      const row = authenticatedPage.getByRole('row').filter({ hasText: name });
      await row.getByRole('button', { name: /Compare/i }).click();
    }

    // Compare tray shows 4 players
    const tray = authenticatedPage.getByTestId('compare-tray');
    await expect(tray.getByText(/Compare \(4\)/i)).toBeVisible();
    for (const name of playerNames) {
      await expect(tray.getByText(new RegExp(name))).toBeVisible();
    }

    // 5th player compare button should be disabled
    const marnerRow = authenticatedPage.getByRole('row').filter({ hasText: 'Mitch Marner' });
    await expect(marnerRow.getByRole('button', { name: /Compare/i })).toBeDisabled();
  });

  test('compare tray shows stat comparison with goals, assists, and points', async ({
    authenticatedPage,
  }) => {
    await setupCompareMocks(authenticatedPage);
    await authenticatedPage.goto(`/draft/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /Draft Room/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Add two players
    const mcdavidRow = authenticatedPage.getByRole('row').filter({ hasText: 'Connor McDavid' });
    await mcdavidRow.getByRole('button', { name: /Compare/i }).click();
    const matthewsRow = authenticatedPage.getByRole('row').filter({ hasText: 'Auston Matthews' });
    await matthewsRow.getByRole('button', { name: /Compare/i }).click();

    const tray = authenticatedPage.getByTestId('compare-tray');

    // Verify column headers in compare table
    await expect(tray.getByRole('columnheader', { name: 'Goals' })).toBeVisible();
    await expect(tray.getByRole('columnheader', { name: 'Assists' })).toBeVisible();
    await expect(tray.getByRole('columnheader', { name: 'Points' })).toBeVisible();

    // Verify McDavid's stats in compare (8G, 12A, 20Pts)
    const mcdavidCompareRow = tray.getByRole('row').filter({ hasText: 'Connor McDavid' });
    await expect(mcdavidCompareRow).toBeVisible();

    // Verify Matthews stats in compare (6G, 5A, 11Pts)
    const matthewsCompareRow = tray.getByRole('row').filter({ hasText: 'Auston Matthews' });
    await expect(matthewsCompareRow).toBeVisible();
  });

  test('players can be removed from the compare tray', async ({
    authenticatedPage,
  }) => {
    await setupCompareMocks(authenticatedPage);
    await authenticatedPage.goto(`/draft/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /Draft Room/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Add two players
    const mcdavidRow = authenticatedPage.getByRole('row').filter({ hasText: 'Connor McDavid' });
    await mcdavidRow.getByRole('button', { name: /Compare/i }).click();
    const matthewsRow = authenticatedPage.getByRole('row').filter({ hasText: 'Auston Matthews' });
    await matthewsRow.getByRole('button', { name: /Compare/i }).click();

    const tray = authenticatedPage.getByTestId('compare-tray');
    await expect(tray.getByText(/Compare \(2\)/i)).toBeVisible();

    // Remove McDavid via the remove button
    await tray.getByRole('button', { name: /Remove Connor McDavid/i }).click();

    // Tray should now show 1 player
    await expect(tray.getByText(/Compare \(1\)/i)).toBeVisible();
    await expect(tray.getByText(/Connor McDavid/)).not.toBeVisible();
    await expect(tray.getByText(/Auston Matthews/)).toBeVisible();

    // Remove last player — tray disappears
    await tray.getByRole('button', { name: /Remove Auston Matthews/i }).click();
    await expect(authenticatedPage.getByTestId('compare-tray')).not.toBeVisible();
  });

  test('compare tray persists across draft page interactions like filtering', async ({
    authenticatedPage,
  }) => {
    await setupCompareMocks(authenticatedPage);
    await authenticatedPage.goto(`/draft/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /Draft Room/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Add a forward to compare
    const mcdavidRow = authenticatedPage.getByRole('row').filter({ hasText: 'Connor McDavid' });
    await mcdavidRow.getByRole('button', { name: /Compare/i }).click();

    const tray = authenticatedPage.getByTestId('compare-tray');
    await expect(tray.getByText(/Compare \(1\)/i)).toBeVisible();

    // Switch to Defense filter
    await authenticatedPage.locator('label:has-text("Defense")').click();
    await expect(authenticatedPage.getByText('Cale Makar')).toBeVisible();
    // McDavid should not be in the available players table (but still in compare tray)
    const skatersSection = authenticatedPage.getByText(/Skaters \(/i).locator('..');
    await expect(skatersSection.getByText('Connor McDavid')).not.toBeVisible();

    // Compare tray should still show McDavid
    await expect(tray.getByText(/Connor McDavid/)).toBeVisible();
    await expect(tray.getByText(/Compare \(1\)/i)).toBeVisible();

    // Switch to Goalies filter
    await authenticatedPage.locator('label:has-text("Goalies")').click();

    // Compare tray should still persist
    await expect(tray.getByText(/Connor McDavid/)).toBeVisible();

    // Switch back to All
    await authenticatedPage.locator('label:has-text("All")').click();

    // Compare tray still intact
    await expect(tray.getByText(/Connor McDavid/)).toBeVisible();
    await expect(tray.getByText(/Compare \(1\)/i)).toBeVisible();
  });
});
