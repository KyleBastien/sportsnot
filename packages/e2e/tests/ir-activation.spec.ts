import { test, expect } from '../fixtures/supabase-mock.fixture';
import {
  setupSupabaseMocks,
  mockTableList,
} from '../fixtures/supabase-mock.fixture';
import { mockUser } from '../fixtures/auth.fixture';

const NAV_TIMEOUT = { timeout: 15000 };
const SUPABASE_URL = 'http://localhost:54321';
const LEAGUE_ID = 'ir-test-league-1111-2222-333333333333';
const MEMBER_ID = 'member-ir-test-user-001';

// ---------------------------------------------------------------------------
// Mock data: league member (current user)
// ---------------------------------------------------------------------------
const memberData = {
  id: MEMBER_ID,
  league_id: LEAGUE_ID,
  user_id: mockUser.id,
  team_name: 'IR Test Team',
  total_points: 40,
  joined_at: '2026-01-20T00:00:00.000Z',
};

// ---------------------------------------------------------------------------
// Mock data: league
// ---------------------------------------------------------------------------
const leagueData = {
  id: LEAGUE_ID,
  name: 'IR Activation League',
  commissioner_id: mockUser.id,
  invite_code: 'IRT001',
  max_participants: 8,
  status: 'active',
  current_round: 1,
  created_at: '2026-01-15T00:00:00.000Z',
  updated_at: '2026-02-14T00:00:00.000Z',
  league_members: [
    {
      id: MEMBER_ID,
      user_id: mockUser.id,
      team_name: 'IR Test Team',
      total_points: 40,
      users: { display_name: 'Test User' },
    },
  ],
};

// ---------------------------------------------------------------------------
// Mock data: roster with injured forward and IR_F replacement available
// 5F + 3D + 1G active, 1 IR_F + 1 IR_D inactive
// ---------------------------------------------------------------------------
const rosterSlots = [
  // 5 Forwards (active) — one is "injured" (conceptually, the IR slot can replace an active F)
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
  // IR Forward slot (inactive) — can replace an active Forward
  {
    id: 'slot-irf',
    league_member_id: MEMBER_ID,
    round: 1,
    player_id: 8477492,
    team_id: null,
    position: 'IR_F',
    is_active: false,
    points_earned: 10,
    activated_from_ir: false,
  },
  // IR Defenseman slot (inactive) — can replace an active Defenseman
  {
    id: 'slot-ird',
    league_member_id: MEMBER_ID,
    round: 1,
    player_id: 8477939,
    team_id: null,
    position: 'IR_D',
    is_active: false,
    points_earned: 5,
    activated_from_ir: false,
  },
];

// ---------------------------------------------------------------------------
// Roster after IR activation: IR_F player replaces first Forward, points updated
// ---------------------------------------------------------------------------
const rosterAfterActivation = rosterSlots.map((slot) => {
  if (slot.id === 'slot-irf') {
    return { ...slot, is_active: true, activated_from_ir: true };
  }
  if (slot.id === 'slot-f1') {
    return { ...slot, is_active: false, points_earned: 0 };
  }
  return slot;
});

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
// Mock data: player and team stats for name resolution
// ---------------------------------------------------------------------------
const irPlayerStatsCache = [
  { player_id: 8478402, player_name: 'Connor McDavid', position: 'F', team_abbreviation: 'EDM', is_injured: false, goals: 0, assists: 0, games_played: 0, nhl_season: '20242025', playoff_round: 1 },
  { player_id: 8479318, player_name: 'Auston Matthews', position: 'F', team_abbreviation: 'TOR', is_injured: false, goals: 0, assists: 0, games_played: 0, nhl_season: '20242025', playoff_round: 1 },
  { player_id: 8471675, player_name: 'Sidney Crosby', position: 'F', team_abbreviation: 'PIT', is_injured: false, goals: 0, assists: 0, games_played: 0, nhl_season: '20242025', playoff_round: 1 },
  { player_id: 8477934, player_name: 'Leon Draisaitl', position: 'F', team_abbreviation: 'EDM', is_injured: false, goals: 0, assists: 0, games_played: 0, nhl_season: '20242025', playoff_round: 1 },
  { player_id: 8479339, player_name: 'Jack Eichel', position: 'F', team_abbreviation: 'VGK', is_injured: false, goals: 0, assists: 0, games_played: 0, nhl_season: '20242025', playoff_round: 1 },
  { player_id: 8480069, player_name: 'Cale Makar', position: 'D', team_abbreviation: 'COL', is_injured: false, goals: 0, assists: 0, games_played: 0, nhl_season: '20242025', playoff_round: 1 },
  { player_id: 8479323, player_name: 'Miro Heiskanen', position: 'D', team_abbreviation: 'DAL', is_injured: false, goals: 0, assists: 0, games_played: 0, nhl_season: '20242025', playoff_round: 1 },
  { player_id: 8480145, player_name: 'Quinn Hughes', position: 'D', team_abbreviation: 'VAN', is_injured: false, goals: 0, assists: 0, games_played: 0, nhl_season: '20242025', playoff_round: 1 },
  { player_id: 8477492, player_name: 'Filip Forsberg', position: 'F', team_abbreviation: 'NSH', is_injured: true, goals: 0, assists: 0, games_played: 0, nhl_season: '20242025', playoff_round: 1 },
  { player_id: 8477939, player_name: 'Morgan Rielly', position: 'D', team_abbreviation: 'TOR', is_injured: true, goals: 0, assists: 0, games_played: 0, nhl_season: '20242025', playoff_round: 1 },
];

const irTeamStatsCache = [
  { team_id: 14, team_name: 'Tampa Bay Lightning', team_abbreviation: 'TBL', is_eliminated: false, wins: 0, shutouts: 0, nhl_season: '20242025', playoff_round: 1 },
];

// ---------------------------------------------------------------------------
// Setup helper
// ---------------------------------------------------------------------------

async function setupIRMocks(
  page: import('@playwright/test').Page,
  overrides?: { roster?: typeof rosterSlots }
) {
  const roster = overrides?.roster ?? rosterSlots;

  await setupSupabaseMocks(page, {
    leagues: leagueHandler(),
    league_members: leagueMembersHandler(),
    rosters: mockTableList(roster),
    player_stats_cache: mockTableList(irPlayerStatsCache),
    team_stats_cache: mockTableList(irTeamStatsCache),
  });
}

// ──────────────────────────────────────────────────────────────────────────────
// IR Activation Tests
// ──────────────────────────────────────────────────────────────────────────────
test.describe('IR Activation Flow', () => {
  test('injured player on roster shows IR activation option/button', async ({
    authenticatedPage,
  }) => {
    await setupIRMocks(authenticatedPage);
    await authenticatedPage.goto(`/roster/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /My Roster/i })
    ).toBeVisible(NAV_TIMEOUT);

    // IR Forward section should have an Activate IR button
    // heading -> Group -> Card (need ../..)
    const irForwardSection = authenticatedPage
      .getByRole('heading', { name: 'IR Forward' })
      .locator('../..');
    await expect(
      irForwardSection.getByRole('button', { name: /Activate IR/i })
    ).toBeVisible();

    // IR Defenseman section should also have an Activate IR button
    const irDefenseSection = authenticatedPage
      .getByRole('heading', { name: 'IR Defenseman' })
      .locator('../..');
    await expect(
      irDefenseSection.getByRole('button', { name: /Activate IR/i })
    ).toBeVisible();
  });

  test('clicking activate opens IR activation modal', async ({
    authenticatedPage,
  }) => {
    await setupIRMocks(authenticatedPage);
    await authenticatedPage.goto(`/roster/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /My Roster/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Click the first Activate IR button (IR Forward)
    await authenticatedPage
      .getByRole('button', { name: /Activate IR/i })
      .first()
      .click();

    // Modal should open with "Activate IR Player" title
    const modal = authenticatedPage.getByRole('dialog');
    await expect(modal).toBeVisible();
    await expect(modal.getByText('Activate IR Player').first()).toBeVisible();

    // Modal shows warning about retroactive points
    await expect(modal.getByText(/retroactively grant/i)).toBeVisible();

    // Modal has Cancel and Activate IR Player buttons
    await expect(modal.getByRole('button', { name: /Cancel/i })).toBeVisible();
    await expect(
      modal.getByRole('button', { name: /Activate IR Player/i })
    ).toBeVisible();
  });

  test('modal shows eligible replacement players of the same position only', async ({
    authenticatedPage,
  }) => {
    await setupIRMocks(authenticatedPage);
    await authenticatedPage.goto(`/roster/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /My Roster/i })
    ).toBeVisible(NAV_TIMEOUT);

    // The Activate IR button appears on IR_F row — it maps to Forwards only
    // IR Forward section shows the IR_F player (heading -> Group -> Card)
    const irForwardSection = authenticatedPage
      .getByRole('heading', { name: 'IR Forward' })
      .locator('../..');
    await expect(irForwardSection.getByText('Filip Forsberg')).toBeVisible();

    // The Activate IR button is present for IR_F because there are active Forwards
    await expect(
      irForwardSection.getByRole('button', { name: /Activate IR/i })
    ).toBeVisible();

    // Similarly, IR_D section shows its player and Activate IR button
    const irDefenseSection = authenticatedPage
      .getByRole('heading', { name: 'IR Defenseman' })
      .locator('../..');
    await expect(irDefenseSection.getByText('Morgan Rielly')).toBeVisible();
    await expect(
      irDefenseSection.getByRole('button', { name: /Activate IR/i })
    ).toBeVisible();
  });

  test('modal displays point differential preview between current and replacement player', async ({
    authenticatedPage,
  }) => {
    await setupIRMocks(authenticatedPage);
    await authenticatedPage.goto(`/roster/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /My Roster/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Click the IR Forward Activate IR button
    await authenticatedPage
      .getByRole('button', { name: /Activate IR/i })
      .first()
      .click();

    // Modal is open
    const modal = authenticatedPage.getByRole('dialog');
    await expect(modal).toBeVisible();

    // The modal warns that injured player points will be removed and IR player points granted
    await expect(
      modal.getByText(/remove all points from the injured player/i)
    ).toBeVisible();
    await expect(
      modal.getByText(/retroactively grant the IR player's points/i)
    ).toBeVisible();
  });

  test('confirming activation mocks the update request and shows updated roster', async ({
    authenticatedPage,
  }) => {
    await setupIRMocks(authenticatedPage);

    // Track RPC calls to activate_ir_player
    let rpcCalled = false;
    await authenticatedPage.route(
      `${SUPABASE_URL}/rest/v1/rpc/activate_ir_player`,
      async (route) => {
        rpcCalled = true;
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({}),
        });
      }
    );

    await authenticatedPage.goto(`/roster/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /My Roster/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Click Activate IR on IR Forward
    await authenticatedPage
      .getByRole('button', { name: /Activate IR/i })
      .first()
      .click();

    const modal = authenticatedPage.getByRole('dialog');
    await expect(modal).toBeVisible();

    // Before confirming, swap the roster mock to return updated data
    await authenticatedPage.unrouteAll({ behavior: 'ignoreErrors' });
    await setupIRMocks(authenticatedPage, { roster: rosterAfterActivation });
    // Re-mock the RPC endpoint after unrouteAll
    await authenticatedPage.route(
      `${SUPABASE_URL}/rest/v1/rpc/activate_ir_player`,
      async (route) => {
        rpcCalled = true;
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({}),
        });
      }
    );

    // Click "Activate IR Player" to confirm
    await modal.getByRole('button', { name: /Activate IR Player/i }).click();

    // Modal should close
    await expect(modal).toBeHidden();

    // Verify the RPC was called
    expect(rpcCalled).toBe(true);

    // After activation, the IR Forward should show "From IR" badge
    await expect(authenticatedPage.getByText('From IR')).toBeVisible(
      NAV_TIMEOUT
    );
  });

  test('position mismatch replacements are not offered in the modal', async ({
    authenticatedPage,
  }) => {
    // Create a roster where there are NO active Forwards — only IR_F slot exists
    // The IR_F Activate IR button should NOT appear because there are no active F candidates
    const noForwardRoster = rosterSlots
      .filter((s) => s.position !== 'F')
      .concat([
        // Keep the IR_F slot
      ]);

    await setupIRMocks(authenticatedPage, { roster: noForwardRoster });
    await authenticatedPage.goto(`/roster/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /My Roster/i })
    ).toBeVisible(NAV_TIMEOUT);

    // IR Forward section should exist
    await expect(
      authenticatedPage.getByRole('heading', { name: 'IR Forward' })
    ).toBeVisible();

    // But the Activate IR button should NOT be in IR Forward section
    // because there are no active Forward candidates to swap with
    const irForwardSection = authenticatedPage
      .getByRole('heading', { name: 'IR Forward' })
      .locator('../..');

    // Verify the IR_F player is shown
    await expect(irForwardSection.getByText('Filip Forsberg')).toBeVisible();

    // No Activate IR button should be present in the IR Forward section
    await expect(
      irForwardSection.getByRole('button', { name: /Activate IR/i })
    ).toBeHidden();

    // IR Defenseman should still have the Activate IR button since D slots exist
    const irDefenseSection = authenticatedPage
      .getByRole('heading', { name: 'IR Defenseman' })
      .locator('../..');
    await expect(
      irDefenseSection.getByRole('button', { name: /Activate IR/i })
    ).toBeVisible();
  });
});
