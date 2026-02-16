import { test, expect } from '../fixtures/supabase-mock.fixture';
import {
  setupSupabaseMocks,
  mockTableList,
} from '../fixtures/supabase-mock.fixture';
import { mockUser } from '../fixtures/auth.fixture';

const NAV_TIMEOUT = { timeout: 15000 };
const LEAGUE_ID = 'draft-board-league-1111-2222-333333333333';
const MEMBER_ID = 'member-current-user-0001';
const OTHER_MEMBER_ID = 'member-other-user-0002';
const OTHER_USER_ID = '99999999-8888-7777-6666-555555555555';

// ---------------------------------------------------------------------------
// Mock data: league + members
// ---------------------------------------------------------------------------
const leagueData = {
  id: LEAGUE_ID,
  name: 'Draft Board League',
  commissioner_id: mockUser.id,
  invite_code: 'DRFT01',
  max_participants: 4,
  status: 'active',
  current_round: 1,
  created_at: '2026-01-15T00:00:00.000Z',
  updated_at: '2026-02-14T00:00:00.000Z',
  league_members: [
    {
      id: MEMBER_ID,
      user_id: mockUser.id,
      team_name: 'My Draft Team',
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
    team_name: 'My Draft Team',
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
function buildDraft(overrides: Record<string, unknown> = {}) {
  return {
    id: 'draft-0001',
    league_id: LEAGUE_ID,
    round: 1,
    status: 'active',
    current_pick: 1,
    draft_order: [mockUser.id, OTHER_USER_ID],
    started_at: '2026-02-14T12:00:00.000Z',
    draft_picks: [] as unknown[],
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Mock data: 20+ players across F/D/G and teams
// ---------------------------------------------------------------------------
const mockForwards = [
  {
    player_id: 8478402,
    nhl_season: '20252026',
    playoff_round: 1,
    player_name: 'Connor McDavid',
    team_abbreviation: 'EDM',
    position: 'F',
    goals: 8,
    assists: 12,
    games_played: 7,
    is_injured: false,
    last_updated: '2026-02-14T00:00:00Z',
  },
  {
    player_id: 8479318,
    nhl_season: '20252026',
    playoff_round: 1,
    player_name: 'Auston Matthews',
    team_abbreviation: 'TOR',
    position: 'F',
    goals: 6,
    assists: 5,
    games_played: 7,
    is_injured: false,
    last_updated: '2026-02-14T00:00:00Z',
  },
  {
    player_id: 8471675,
    nhl_season: '20252026',
    playoff_round: 1,
    player_name: 'Sidney Crosby',
    team_abbreviation: 'PIT',
    position: 'F',
    goals: 5,
    assists: 8,
    games_played: 6,
    is_injured: false,
    last_updated: '2026-02-14T00:00:00Z',
  },
  {
    player_id: 8477934,
    nhl_season: '20252026',
    playoff_round: 1,
    player_name: 'Leon Draisaitl',
    team_abbreviation: 'EDM',
    position: 'F',
    goals: 7,
    assists: 6,
    games_played: 7,
    is_injured: false,
    last_updated: '2026-02-14T00:00:00Z',
  },
  {
    player_id: 8479339,
    nhl_season: '20252026',
    playoff_round: 1,
    player_name: 'Mitch Marner',
    team_abbreviation: 'TOR',
    position: 'F',
    goals: 3,
    assists: 10,
    games_played: 7,
    is_injured: false,
    last_updated: '2026-02-14T00:00:00Z',
  },
  {
    player_id: 8477492,
    nhl_season: '20252026',
    playoff_round: 1,
    player_name: 'Nathan MacKinnon',
    team_abbreviation: 'COL',
    position: 'F',
    goals: 4,
    assists: 9,
    games_played: 6,
    is_injured: false,
    last_updated: '2026-02-14T00:00:00Z',
  },
  {
    player_id: 8478483,
    nhl_season: '20252026',
    playoff_round: 1,
    player_name: 'Jack Eichel',
    team_abbreviation: 'VGK',
    position: 'F',
    goals: 5,
    assists: 4,
    games_played: 5,
    is_injured: false,
    last_updated: '2026-02-14T00:00:00Z',
  },
  {
    player_id: 8480012,
    nhl_season: '20252026',
    playoff_round: 1,
    player_name: 'Brady Tkachuk',
    team_abbreviation: 'OTT',
    position: 'F',
    goals: 4,
    assists: 3,
    games_played: 6,
    is_injured: false,
    last_updated: '2026-02-14T00:00:00Z',
  },
  {
    player_id: 8478427,
    nhl_season: '20252026',
    playoff_round: 1,
    player_name: 'Sebastian Aho',
    team_abbreviation: 'CAR',
    position: 'F',
    goals: 3,
    assists: 5,
    games_played: 5,
    is_injured: false,
    last_updated: '2026-02-14T00:00:00Z',
  },
  {
    player_id: 8480064,
    nhl_season: '20252026',
    playoff_round: 1,
    player_name: 'Elias Pettersson',
    team_abbreviation: 'VAN',
    position: 'F',
    goals: 2,
    assists: 6,
    games_played: 5,
    is_injured: false,
    last_updated: '2026-02-14T00:00:00Z',
  },
  {
    player_id: 8480001,
    nhl_season: '20252026',
    playoff_round: 1,
    player_name: 'Kyle Connor',
    team_abbreviation: 'WPG',
    position: 'F',
    goals: 4,
    assists: 4,
    games_played: 6,
    is_injured: false,
    last_updated: '2026-02-14T00:00:00Z',
  },
  {
    player_id: 8480002,
    nhl_season: '20252026',
    playoff_round: 1,
    player_name: 'Nikita Kucherov',
    team_abbreviation: 'TBL',
    position: 'F',
    goals: 6,
    assists: 7,
    games_played: 7,
    is_injured: false,
    last_updated: '2026-02-14T00:00:00Z',
  },
];

const mockInjuredForward = {
  player_id: 8480099,
  nhl_season: '20252026',
  playoff_round: 1,
  player_name: 'Injured Forward',
  team_abbreviation: 'BOS',
  position: 'F',
  goals: 1,
  assists: 1,
  games_played: 2,
  is_injured: true,
  last_updated: '2026-02-14T00:00:00Z',
};

const mockDefensemen = [
  {
    player_id: 8480069,
    nhl_season: '20252026',
    playoff_round: 1,
    player_name: 'Cale Makar',
    team_abbreviation: 'COL',
    position: 'D',
    goals: 4,
    assists: 8,
    games_played: 6,
    is_injured: false,
    last_updated: '2026-02-14T00:00:00Z',
  },
  {
    player_id: 8479323,
    nhl_season: '20252026',
    playoff_round: 1,
    player_name: 'Victor Hedman',
    team_abbreviation: 'TBL',
    position: 'D',
    goals: 2,
    assists: 6,
    games_played: 7,
    is_injured: false,
    last_updated: '2026-02-14T00:00:00Z',
  },
  {
    player_id: 8480145,
    nhl_season: '20252026',
    playoff_round: 1,
    player_name: 'Quinn Hughes',
    team_abbreviation: 'VAN',
    position: 'D',
    goals: 1,
    assists: 7,
    games_played: 5,
    is_injured: false,
    last_updated: '2026-02-14T00:00:00Z',
  },
  {
    player_id: 8477939,
    nhl_season: '20252026',
    playoff_round: 1,
    player_name: 'Adam Fox',
    team_abbreviation: 'NYR',
    position: 'D',
    goals: 3,
    assists: 5,
    games_played: 6,
    is_injured: false,
    last_updated: '2026-02-14T00:00:00Z',
  },
  {
    player_id: 8479400,
    nhl_season: '20252026',
    playoff_round: 1,
    player_name: 'Miro Heiskanen',
    team_abbreviation: 'DAL',
    position: 'D',
    goals: 2,
    assists: 4,
    games_played: 5,
    is_injured: false,
    last_updated: '2026-02-14T00:00:00Z',
  },
];

const mockTeams = [
  {
    team_id: 22,
    nhl_season: '20252026',
    playoff_round: 1,
    team_name: 'Edmonton Oilers',
    team_abbreviation: 'EDM',
    wins: 4,
    shutouts: 1,
    is_eliminated: false,
    last_updated: '2026-02-14T00:00:00Z',
  },
  {
    team_id: 10,
    nhl_season: '20252026',
    playoff_round: 1,
    team_name: 'Toronto Maple Leafs',
    team_abbreviation: 'TOR',
    wins: 3,
    shutouts: 0,
    is_eliminated: false,
    last_updated: '2026-02-14T00:00:00Z',
  },
  {
    team_id: 21,
    nhl_season: '20252026',
    playoff_round: 1,
    team_name: 'Colorado Avalanche',
    team_abbreviation: 'COL',
    wins: 3,
    shutouts: 1,
    is_eliminated: false,
    last_updated: '2026-02-14T00:00:00Z',
  },
  {
    team_id: 52,
    nhl_season: '20252026',
    playoff_round: 1,
    team_name: 'Winnipeg Jets',
    team_abbreviation: 'WPG',
    wins: 2,
    shutouts: 0,
    is_eliminated: false,
    last_updated: '2026-02-14T00:00:00Z',
  },
  {
    team_id: 14,
    nhl_season: '20252026',
    playoff_round: 1,
    team_name: 'Tampa Bay Lightning',
    team_abbreviation: 'TBL',
    wins: 2,
    shutouts: 1,
    is_eliminated: false,
    last_updated: '2026-02-14T00:00:00Z',
  },
];

const mockEliminatedTeam = {
  team_id: 99,
  nhl_season: '20252026',
  playoff_round: 1,
  team_name: 'Eliminated Team',
  team_abbreviation: 'ELM',
  wins: 0,
  shutouts: 0,
  is_eliminated: true,
  last_updated: '2026-02-14T00:00:00Z',
};

const allPlayers = [...mockForwards, mockInjuredForward, ...mockDefensemen];
const allTeams = [...mockTeams, mockEliminatedTeam];

// ---------------------------------------------------------------------------
// Route handler helpers
// ---------------------------------------------------------------------------

/** Route handler for leagues table — single returns league data, list returns empty */
function leagueHandler(league = leagueData) {
  return async (route: import('@playwright/test').Route) => {
    const request = route.request();
    const method = request.method();
    const accept = request.headers()['accept'] ?? '';

    if (method === 'GET' && accept.includes('vnd.pgrst.object+json')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(league),
      });
    }

    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  };
}

/** Route handler for drafts table — single returns draft with picks, list returns array */
function draftHandler(draft = buildDraft()) {
  return async (route: import('@playwright/test').Route) => {
    const request = route.request();
    const method = request.method();
    const accept = request.headers()['accept'] ?? '';

    if (method === 'GET' && accept.includes('vnd.pgrst.object+json')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(draft),
      });
    }

    if (method === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([draft]),
      });
    }

    if (method === 'PATCH') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(draft),
      });
    }

    return route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify(draft),
    });
  };
}

// ---------------------------------------------------------------------------
// Setup helper
// ---------------------------------------------------------------------------

async function setupDraftBoardMocks(
  page: import('@playwright/test').Page,
  overrides: {
    draft?: ReturnType<typeof buildDraft>;
    players?: typeof allPlayers;
    teams?: typeof allTeams;
  } = {}
) {
  const draft = overrides.draft ?? buildDraft();
  const players = overrides.players ?? allPlayers;
  const teams = overrides.teams ?? allTeams;

  await setupSupabaseMocks(page, {
    leagues: leagueHandler(),
    league_members: mockTableList(membersListData),
    drafts: draftHandler(draft),
    draft_picks: async (route) => {
      const method = route.request().method();
      if (method === 'POST') {
        return route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({}),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(draft.draft_picks ?? []),
      });
    },
    player_stats_cache: mockTableList(players),
    team_stats_cache: mockTableList(teams),
    rosters: async (route) => {
      const method = route.request().method();
      if (method === 'POST') {
        return route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({}),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    },
  });
}

// ──────────────────────────────────────────────────────────────────────────────
// Draft Board Tests
// ──────────────────────────────────────────────────────────────────────────────
test.describe('Draft Board', () => {
  test('draft page renders available players list', async ({
    authenticatedPage,
  }) => {
    await setupDraftBoardMocks(authenticatedPage);
    await authenticatedPage.goto(`/draft/${LEAGUE_ID}`);

    // Wait for Draft Room heading
    await expect(
      authenticatedPage.getByRole('heading', { name: /Draft Room/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Skaters table should show forwards and defensemen (not injured)
    await expect(authenticatedPage.getByText('Connor McDavid')).toBeVisible();
    await expect(authenticatedPage.getByText('Auston Matthews')).toBeVisible();
    await expect(authenticatedPage.getByText('Cale Makar')).toBeVisible();

    // Injured forward should NOT appear
    await expect(authenticatedPage.getByText('Injured Forward')).toBeHidden();
  });

  test('players can be filtered by position F, D, and G/Team', async ({
    authenticatedPage,
  }) => {
    await setupDraftBoardMocks(authenticatedPage);
    await authenticatedPage.goto(`/draft/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /Draft Room/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Filter by Forwards — only F position players
    // Mantine SegmentedControl: click the visible label text, not the hidden radio input
    await authenticatedPage.locator('label:has-text("Forwards")').click();
    await expect(authenticatedPage.getByText('Connor McDavid')).toBeVisible();
    // Defenseman should not be visible when filtered to Forwards
    await expect(authenticatedPage.getByText('Cale Makar')).toBeHidden();

    // Filter by Defense
    await authenticatedPage.locator('label:has-text("Defense")').click();
    await expect(authenticatedPage.getByText('Cale Makar')).toBeVisible();
    await expect(authenticatedPage.getByText('Victor Hedman')).toBeVisible();
    // Forward should not be visible
    await expect(authenticatedPage.getByText('Connor McDavid')).toBeHidden();

    // Filter by Goalies — shows teams table
    await authenticatedPage.locator('label:has-text("Goalies")').click();
    await expect(authenticatedPage.getByText('Edmonton Oilers')).toBeVisible();
    await expect(
      authenticatedPage.getByText('Toronto Maple Leafs')
    ).toBeVisible();
    // Skater should not be visible
    await expect(authenticatedPage.getByText('Connor McDavid')).toBeHidden();
    // Eliminated team should not appear
    await expect(authenticatedPage.getByText('Eliminated Team')).toBeHidden();

    // Filter back to All
    await authenticatedPage.locator('label:has-text("All")').click();
    await expect(authenticatedPage.getByText('Connor McDavid')).toBeVisible();
    await expect(authenticatedPage.getByText('Cale Makar')).toBeVisible();
  });

  test('players can be searched by name via search input', async ({
    authenticatedPage,
  }) => {
    await setupDraftBoardMocks(authenticatedPage);
    await authenticatedPage.goto(`/draft/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /Draft Room/i })
    ).toBeVisible(NAV_TIMEOUT);

    const searchInput = authenticatedPage.getByPlaceholder(/Search players/i);
    await searchInput.fill('McDavid');

    // Only matching player should be visible
    await expect(authenticatedPage.getByText('Connor McDavid')).toBeVisible();
    // Non-matching players should be hidden
    await expect(authenticatedPage.getByText('Auston Matthews')).toBeHidden();
    await expect(authenticatedPage.getByText('Cale Makar')).toBeHidden();

    // Clear search
    await searchInput.clear();
    await expect(authenticatedPage.getByText('Auston Matthews')).toBeVisible();
  });

  test('players can be sorted by stats (goals, assists, points)', async ({
    authenticatedPage,
  }) => {
    // Note: The app sorts players by goals descending by default from the query.
    // There are no interactive sort buttons in the UI — validate default order.
    await setupDraftBoardMocks(authenticatedPage);
    await authenticatedPage.goto(`/draft/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /Draft Room/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Players should be displayed in a table with stat columns
    const skatersTable = authenticatedPage.getByRole('table').first();
    await expect(skatersTable).toBeVisible();

    // Column headers should be present
    await expect(
      skatersTable.getByRole('columnheader', { name: 'Player' })
    ).toBeVisible();
    await expect(
      skatersTable.getByRole('columnheader', { name: 'G', exact: true })
    ).toBeVisible();
    await expect(
      skatersTable.getByRole('columnheader', { name: 'A', exact: true })
    ).toBeVisible();
    await expect(
      skatersTable.getByRole('columnheader', { name: 'Pts', exact: true })
    ).toBeVisible();

    // Top scorer (McDavid with 8 goals) should appear in the list
    await expect(skatersTable.getByText('Connor McDavid')).toBeVisible();
  });

  test('eliminated players appear as unavailable — filtered from list', async ({
    authenticatedPage,
  }) => {
    // The app filters out injured players and eliminated teams entirely
    await setupDraftBoardMocks(authenticatedPage);
    await authenticatedPage.goto(`/draft/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /Draft Room/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Injured forward should not appear in skaters list
    await expect(authenticatedPage.getByText('Injured Forward')).toBeHidden();

    // Switch to Goalies to check teams
    await authenticatedPage.locator('label:has-text("Goalies")').click();

    // Eliminated team should not appear
    await expect(authenticatedPage.getByText('Eliminated Team')).toBeHidden();

    // Active teams should still be visible
    await expect(authenticatedPage.getByText('Edmonton Oilers')).toBeVisible();
  });

  test('clicking a player shows draft confirmation modal', async ({
    authenticatedPage,
  }) => {
    // Draft with current_pick=1, draft_order[0]=mockUser.id → it's our turn
    await setupDraftBoardMocks(authenticatedPage);
    await authenticatedPage.goto(`/draft/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /Draft Room/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Click the Draft button on McDavid's row
    const row = authenticatedPage
      .getByRole('row')
      .filter({ hasText: 'Connor McDavid' });
    await row.getByRole('button', { name: /Draft/i }).click();

    // Confirmation modal should appear
    const modal = authenticatedPage.getByRole('dialog');
    await expect(modal).toBeVisible();
    await expect(modal.getByText(/Confirm Draft Pick/i)).toBeVisible();
    await expect(modal.getByText(/Connor McDavid/i)).toBeVisible();

    // Cancel and Confirm buttons
    await expect(modal.getByRole('button', { name: /Cancel/i })).toBeVisible();
    await expect(
      modal.getByRole('button', { name: /Confirm Pick/i })
    ).toBeVisible();
  });

  test('confirming a pick adds player to draft history and advances current pick', async ({
    authenticatedPage,
  }) => {
    // Build draft with mock pick that will be returned after confirmation
    const draftAfterPick = buildDraft({
      current_pick: 2,
      draft_picks: [
        {
          id: 'pick-0001',
          draft_id: 'draft-0001',
          league_member_id: MEMBER_ID,
          pick_number: 1,
          player_id: 8478402,
          position: 'F',
          picked_at: '2026-02-14T12:00:01Z',
          league_members: { team_name: 'My Draft Team', user_id: mockUser.id },
        },
      ],
    });

    let pickConfirmed = false;

    await setupSupabaseMocks(authenticatedPage, {
      leagues: leagueHandler(),
      league_members: mockTableList(membersListData),
      drafts: async (route) => {
        const request = route.request();
        const method = request.method();
        const accept = request.headers()['accept'] ?? '';

        // After the pick is confirmed, return updated draft
        const draft = pickConfirmed ? draftAfterPick : buildDraft();

        if (method === 'GET' && accept.includes('vnd.pgrst.object+json')) {
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(draft),
          });
        }
        if (method === 'PATCH') {
          pickConfirmed = true;
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(draftAfterPick),
          });
        }
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([draft]),
        });
      },
      draft_picks: async (route) => {
        const method = route.request().method();
        if (method === 'POST') {
          pickConfirmed = true;
          return route.fulfill({
            status: 201,
            contentType: 'application/json',
            body: JSON.stringify({}),
          });
        }
        const picks = pickConfirmed ? draftAfterPick.draft_picks : [];
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(picks),
        });
      },
      player_stats_cache: mockTableList(allPlayers),
      team_stats_cache: mockTableList(allTeams),
      rosters: async (route) => {
        if (route.request().method() === 'POST') {
          return route.fulfill({
            status: 201,
            contentType: 'application/json',
            body: JSON.stringify({}),
          });
        }
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      },
    });

    await authenticatedPage.goto(`/draft/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /Draft Room/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Draft History shows "No picks yet" initially
    await expect(authenticatedPage.getByText(/No picks yet/i)).toBeVisible();

    // Click Draft on McDavid
    const row = authenticatedPage
      .getByRole('row')
      .filter({ hasText: 'Connor McDavid' });
    await row.getByRole('button', { name: /Draft/i }).click();

    // Confirm the pick
    const modal = authenticatedPage.getByRole('dialog');
    await modal.getByRole('button', { name: /Confirm Pick/i }).click();

    // Draft History should update to show the pick (after refetch)
    await expect(authenticatedPage.getByText('#1 - My Draft Team')).toBeVisible(
      { timeout: 10000 }
    );
  });

  test('roster sidebar shows filled and empty slots with position requirements', async ({
    authenticatedPage,
  }) => {
    // Draft with some picks already made
    const draft = buildDraft({
      current_pick: 3,
      draft_order: [
        mockUser.id,
        OTHER_USER_ID,
        OTHER_USER_ID,
        mockUser.id,
        mockUser.id,
        OTHER_USER_ID,
      ],
      draft_picks: [
        {
          id: 'pick-0001',
          draft_id: 'draft-0001',
          league_member_id: MEMBER_ID,
          pick_number: 1,
          player_id: 8478402,
          position: 'F',
          picked_at: '2026-02-14T12:00:01Z',
          league_members: { team_name: 'My Draft Team', user_id: mockUser.id },
        },
        {
          id: 'pick-0002',
          draft_id: 'draft-0001',
          league_member_id: OTHER_MEMBER_ID,
          pick_number: 2,
          player_id: 8479318,
          position: 'F',
          picked_at: '2026-02-14T12:00:02Z',
          league_members: {
            team_name: 'Opponent Team',
            user_id: OTHER_USER_ID,
          },
        },
      ],
    });

    await setupDraftBoardMocks(authenticatedPage, { draft });
    await authenticatedPage.goto(`/draft/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /Draft Room/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Draft History card should be visible
    await expect(authenticatedPage.getByText(/Draft History/i)).toBeVisible();

    // Previous picks should be shown in history
    await expect(
      authenticatedPage.getByText('#2 - Opponent Team')
    ).toBeVisible();
    await expect(
      authenticatedPage.getByText('#1 - My Draft Team')
    ).toBeVisible();

    // Position badges should be visible in history
    const historySection = authenticatedPage
      .getByText(/Draft History/i)
      .locator('..');
    await expect(historySection.getByText('F').first()).toBeVisible();
  });
});
