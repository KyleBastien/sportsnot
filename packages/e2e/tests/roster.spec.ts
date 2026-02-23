import { test, expect } from '../fixtures/supabase-mock.fixture';
import {
  setupSupabaseMocks,
  mockTableList,
} from '../fixtures/supabase-mock.fixture';
import { mockUser } from '../fixtures/auth.fixture';

const NAV_TIMEOUT = { timeout: 15000 };
const LEAGUE_ID = 'roster-league-1111-2222-333333333333';
const MEMBER_ID = 'member-current-user-roster-001';

// ---------------------------------------------------------------------------
// Mock data: league member (current user)
// ---------------------------------------------------------------------------
const memberData = {
  id: MEMBER_ID,
  league_id: LEAGUE_ID,
  user_id: mockUser.id,
  team_name: 'My Roster Team',
  total_points: 42,
  joined_at: '2026-01-20T00:00:00.000Z',
};

// ---------------------------------------------------------------------------
// Mock data: league
// ---------------------------------------------------------------------------
const leagueData = {
  id: LEAGUE_ID,
  name: 'Roster Test League',
  commissioner_id: mockUser.id,
  invite_code: 'RST001',
  max_participants: 8,
  status: 'active',
  current_round: 1,
  created_at: '2026-01-15T00:00:00.000Z',
  updated_at: '2026-02-14T00:00:00.000Z',
  league_members: [
    {
      id: MEMBER_ID,
      user_id: mockUser.id,
      team_name: 'My Roster Team',
      total_points: 42,
      users: { display_name: 'Test User' },
    },
  ],
};

// ---------------------------------------------------------------------------
// Mock data: full roster — 5F + 3D + 1G active, 1 IR_F + 1 IR_D inactive
// ---------------------------------------------------------------------------
const rosterSlots = [
  // 5 Forwards (active)
  {
    id: 'slot-f1',
    league_member_id: MEMBER_ID,
    round: 1,
    player_id: 8478402,
    team_id: null,
    position: 'F',
    is_active: true,
    points_earned: 8,
    activated_from_ir: false,
  },
  {
    id: 'slot-f2',
    league_member_id: MEMBER_ID,
    round: 1,
    player_id: 8479318,
    team_id: null,
    position: 'F',
    is_active: true,
    points_earned: 5,
    activated_from_ir: false,
  },
  {
    id: 'slot-f3',
    league_member_id: MEMBER_ID,
    round: 1,
    player_id: 8471675,
    team_id: null,
    position: 'F',
    is_active: true,
    points_earned: 6,
    activated_from_ir: false,
  },
  {
    id: 'slot-f4',
    league_member_id: MEMBER_ID,
    round: 1,
    player_id: 8477934,
    team_id: null,
    position: 'F',
    is_active: true,
    points_earned: 7,
    activated_from_ir: false,
  },
  {
    id: 'slot-f5',
    league_member_id: MEMBER_ID,
    round: 1,
    player_id: 8479339,
    team_id: null,
    position: 'F',
    is_active: true,
    points_earned: 3,
    activated_from_ir: false,
  },
  // 3 Defensemen (active)
  {
    id: 'slot-d1',
    league_member_id: MEMBER_ID,
    round: 1,
    player_id: 8480069,
    team_id: null,
    position: 'D',
    is_active: true,
    points_earned: 4,
    activated_from_ir: false,
  },
  {
    id: 'slot-d2',
    league_member_id: MEMBER_ID,
    round: 1,
    player_id: 8479323,
    team_id: null,
    position: 'D',
    is_active: true,
    points_earned: 2,
    activated_from_ir: false,
  },
  {
    id: 'slot-d3',
    league_member_id: MEMBER_ID,
    round: 1,
    player_id: 8480145,
    team_id: null,
    position: 'D',
    is_active: true,
    points_earned: 3,
    activated_from_ir: false,
  },
  // 1 Goalie (active, uses team_id)
  {
    id: 'slot-g1',
    league_member_id: MEMBER_ID,
    round: 1,
    player_id: null,
    team_id: 14,
    position: 'G',
    is_active: true,
    points_earned: 6,
    activated_from_ir: false,
  },
  // IR slots (inactive)
  {
    id: 'slot-irf',
    league_member_id: MEMBER_ID,
    round: 1,
    player_id: 8477492,
    team_id: null,
    position: 'IR_F',
    is_active: false,
    points_earned: 4,
    activated_from_ir: false,
  },
  {
    id: 'slot-ird',
    league_member_id: MEMBER_ID,
    round: 1,
    player_id: 8477939,
    team_id: null,
    position: 'IR_D',
    is_active: false,
    points_earned: 2,
    activated_from_ir: false,
  },
];

// Total active points: 8+5+6+7+3+4+2+3+6 = 44
const TOTAL_ACTIVE_POINTS = 44;

// ---------------------------------------------------------------------------
// Mock data: player and team stats for name resolution
// ---------------------------------------------------------------------------
const playerStatsCache = [
  {
    player_id: 8478402,
    player_name: 'Connor McDavid',
    position: 'F',
    team_abbreviation: 'EDM',
    is_injured: false,
    goals: 0,
    assists: 0,
    games_played: 0,
    nhl_season: '20242025',
    playoff_round: 1,
  },
  {
    player_id: 8479318,
    player_name: 'Auston Matthews',
    position: 'F',
    team_abbreviation: 'TOR',
    is_injured: false,
    goals: 0,
    assists: 0,
    games_played: 0,
    nhl_season: '20242025',
    playoff_round: 1,
  },
  {
    player_id: 8471675,
    player_name: 'Sidney Crosby',
    position: 'F',
    team_abbreviation: 'PIT',
    is_injured: false,
    goals: 0,
    assists: 0,
    games_played: 0,
    nhl_season: '20242025',
    playoff_round: 1,
  },
  {
    player_id: 8477934,
    player_name: 'Leon Draisaitl',
    position: 'F',
    team_abbreviation: 'EDM',
    is_injured: false,
    goals: 0,
    assists: 0,
    games_played: 0,
    nhl_season: '20242025',
    playoff_round: 1,
  },
  {
    player_id: 8479339,
    player_name: 'Jack Eichel',
    position: 'F',
    team_abbreviation: 'VGK',
    is_injured: false,
    goals: 0,
    assists: 0,
    games_played: 0,
    nhl_season: '20242025',
    playoff_round: 1,
  },
  {
    player_id: 8480069,
    player_name: 'Cale Makar',
    position: 'D',
    team_abbreviation: 'COL',
    is_injured: false,
    goals: 0,
    assists: 0,
    games_played: 0,
    nhl_season: '20242025',
    playoff_round: 1,
  },
  {
    player_id: 8479323,
    player_name: 'Miro Heiskanen',
    position: 'D',
    team_abbreviation: 'DAL',
    is_injured: false,
    goals: 0,
    assists: 0,
    games_played: 0,
    nhl_season: '20242025',
    playoff_round: 1,
  },
  {
    player_id: 8480145,
    player_name: 'Quinn Hughes',
    position: 'D',
    team_abbreviation: 'VAN',
    is_injured: false,
    goals: 0,
    assists: 0,
    games_played: 0,
    nhl_season: '20242025',
    playoff_round: 1,
  },
  {
    player_id: 8477492,
    player_name: 'Filip Forsberg',
    position: 'F',
    team_abbreviation: 'NSH',
    is_injured: true,
    goals: 0,
    assists: 0,
    games_played: 0,
    nhl_season: '20242025',
    playoff_round: 1,
  },
  {
    player_id: 8477939,
    player_name: 'Morgan Rielly',
    position: 'D',
    team_abbreviation: 'TOR',
    is_injured: true,
    goals: 0,
    assists: 0,
    games_played: 0,
    nhl_season: '20242025',
    playoff_round: 1,
  },
];

const teamStatsCache = [
  {
    team_id: 14,
    team_name: 'Tampa Bay Lightning',
    team_abbreviation: 'TBL',
    is_eliminated: false,
    wins: 0,
    shutouts: 0,
    nhl_season: '20242025',
    playoff_round: 1,
  },
];

// ---------------------------------------------------------------------------
// Route handlers
// ---------------------------------------------------------------------------

function leagueHandler() {
  return async (route: import('@playwright/test').Route) => {
    const request = route.request();
    const method = request.method();
    const accept = request.headers()['accept'] ?? '';

    if (method === 'GET' && accept.includes('vnd.pgrst.object+json')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(leagueData),
      });
    }

    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([leagueData]),
    });
  };
}

function leagueMembersHandler() {
  return async (route: import('@playwright/test').Route) => {
    const request = route.request();
    const accept = request.headers()['accept'] ?? '';

    if (accept.includes('vnd.pgrst.object+json')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(memberData),
      });
    }

    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([memberData]),
    });
  };
}

// ---------------------------------------------------------------------------
// Setup helper
// ---------------------------------------------------------------------------

async function setupRosterMocks(
  page: import('@playwright/test').Page,
  overrides?: { roster?: typeof rosterSlots }
) {
  const roster = overrides?.roster ?? rosterSlots;

  await setupSupabaseMocks(page, {
    leagues: leagueHandler(),
    league_members: leagueMembersHandler(),
    rosters: mockTableList(roster),
    player_stats_cache: mockTableList(playerStatsCache),
    team_stats_cache: mockTableList(teamStatsCache),
  });
}

// ──────────────────────────────────────────────────────────────────────────────
// Roster Tests
// ──────────────────────────────────────────────────────────────────────────────
test.describe('Roster Management', () => {
  test('roster page shows all active slots — 5F, 3D, 1G — with player details', async ({
    authenticatedPage,
  }) => {
    await setupRosterMocks(authenticatedPage);
    await authenticatedPage.goto(`/roster/${LEAGUE_ID}`);

    // Wait for heading
    await expect(
      authenticatedPage.getByRole('heading', { name: /My Roster/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Position group headings
    await expect(
      authenticatedPage.getByRole('heading', { name: 'Forward', exact: true })
    ).toBeVisible();
    await expect(
      authenticatedPage.getByRole('heading', {
        name: 'Defenseman',
        exact: true,
      })
    ).toBeVisible();
    await expect(
      authenticatedPage.getByRole('heading', { name: 'Goalie', exact: true })
    ).toBeVisible();

    // Forward section should show 5 players badge
    const forwardCard = authenticatedPage
      .getByRole('heading', { name: 'Forward', exact: true })
      .locator('..');
    await expect(forwardCard.getByText('5 players')).toBeVisible();

    // Defenseman section should show 3 players badge
    const defenseCard = authenticatedPage
      .getByRole('heading', { name: 'Defenseman', exact: true })
      .locator('..');
    await expect(defenseCard.getByText('3 players')).toBeVisible();

    // Goalie section should show 1 player badge
    const goalieCard = authenticatedPage
      .getByRole('heading', { name: 'Goalie', exact: true })
      .locator('..');
    await expect(goalieCard.getByText('1 player')).toBeVisible();

    // Player names are resolved via player/team stats cache
    await expect(authenticatedPage.getByText('Connor McDavid')).toBeVisible();
    await expect(
      authenticatedPage.getByText('Tampa Bay Lightning')
    ).toBeVisible();
  });

  test('IR slots IR_F and IR_D are displayed with correct state', async ({
    authenticatedPage,
  }) => {
    await setupRosterMocks(authenticatedPage);
    await authenticatedPage.goto(`/roster/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /My Roster/i })
    ).toBeVisible(NAV_TIMEOUT);

    // IR group headings
    await expect(
      authenticatedPage.getByRole('heading', { name: 'IR Forward' })
    ).toBeVisible();
    await expect(
      authenticatedPage.getByRole('heading', { name: 'IR Defenseman' })
    ).toBeVisible();

    // IR Forward section shows 1 player
    const irForwardCard = authenticatedPage
      .getByRole('heading', { name: 'IR Forward' })
      .locator('..');
    await expect(irForwardCard.getByText('1 player')).toBeVisible();

    // IR Defenseman section shows 1 player
    const irDefenseCard = authenticatedPage
      .getByRole('heading', { name: 'IR Defenseman' })
      .locator('..');
    await expect(irDefenseCard.getByText('1 player')).toBeVisible();

    // IR players should have Inactive badge
    await expect(authenticatedPage.getByText('Inactive').first()).toBeVisible();

    // IR slots should have Activate IR button since there are active candidates
    await expect(
      authenticatedPage.getByRole('button', { name: /Activate IR/i }).first()
    ).toBeVisible();
  });

  test('each player shows current round stats and earned points', async ({
    authenticatedPage,
  }) => {
    await setupRosterMocks(authenticatedPage);
    await authenticatedPage.goto(`/roster/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /My Roster/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Round info displayed
    await expect(
      authenticatedPage.getByText('Round 1', { exact: true })
    ).toBeVisible();

    // Scoring info displayed
    await expect(authenticatedPage.getByText(/Goal = 1pt/i)).toBeVisible();
    await expect(authenticatedPage.getByText(/Assist = 1pt/i)).toBeVisible();

    // Active badges are shown
    const activeBadges = authenticatedPage.getByText('Active');
    // 9 active slots (5F + 3D + 1G) should show Active badges
    await expect(activeBadges.first()).toBeVisible();

    // Points column shows values — e.g., first forward has 8 points
    const playerRow = authenticatedPage
      .getByRole('row')
      .filter({ hasText: 'Connor McDavid' });
    await expect(playerRow.getByText('8', { exact: true })).toBeVisible();
  });

  test('total team points are calculated and displayed correctly', async ({
    authenticatedPage,
  }) => {
    await setupRosterMocks(authenticatedPage);
    await authenticatedPage.goto(`/roster/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /My Roster/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Total Points card should show sum of active slot points
    await expect(authenticatedPage.getByText('Total Points')).toBeVisible();
    await expect(
      authenticatedPage.getByText(String(TOTAL_ACTIVE_POINTS), { exact: true })
    ).toBeVisible();
  });

  test('roster page is accessible via league dashboard navigation link', async ({
    authenticatedPage,
  }) => {
    await setupRosterMocks(authenticatedPage);

    // Navigate to the league dashboard first
    await authenticatedPage.goto(`/leagues/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /Roster Test League/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Click the "My Roster" button on the dashboard
    await authenticatedPage.getByRole('button', { name: /My Roster/i }).click();

    // Should navigate to roster page
    await expect(
      authenticatedPage.getByRole('heading', { name: /My Roster/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Verify URL changed
    await expect(authenticatedPage).toHaveURL(
      new RegExp(`/roster/${LEAGUE_ID}`)
    );
  });
});
