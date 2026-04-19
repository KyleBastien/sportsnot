import { test, expect } from '../fixtures/supabase-mock.fixture';
import {
  setupSupabaseMocks,
  mockTableList,
} from '../fixtures/supabase-mock.fixture';
import { mockUser } from '../fixtures/auth.fixture';
import { DashboardPage } from '../page-objects';

const NAV_TIMEOUT = { timeout: 15000 };
const MOBILE_VIEWPORT = { width: 375, height: 667 };

const LEAGUE_ID = 'mobile-test-league-1111-2222-333333333333';
const MEMBER_ID = 'member-mobile-user-0001';
const OTHER_MEMBER_ID = 'member-other-mobile-0002';
const OTHER_USER_ID = '99999999-8888-7777-6666-555555555555';

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------
const leagueData = {
  id: LEAGUE_ID,
  name: 'Mobile Test League',
  commissioner_id: mockUser.id,
  invite_code: 'MOB001',
  max_participants: 8,
  status: 'active',
  current_round: 1,
  created_at: '2026-01-15T00:00:00.000Z',
  updated_at: '2026-02-14T00:00:00.000Z',
  league_members: [
    {
      id: MEMBER_ID,
      user_id: mockUser.id,
      team_name: 'Mobile Team',
      total_points: 42,
      users: { display_name: 'Test User', avatar_url: null },
    },
    {
      id: OTHER_MEMBER_ID,
      user_id: OTHER_USER_ID,
      team_name: 'Opponent Mobile',
      total_points: 30,
      users: { display_name: 'Other Player', avatar_url: null },
    },
  ],
};

const memberData = {
  id: MEMBER_ID,
  league_id: LEAGUE_ID,
  user_id: mockUser.id,
  team_name: 'Mobile Team',
  total_points: 42,
  joined_at: '2026-01-20T00:00:00.000Z',
};

const membersListData = [
  {
    id: MEMBER_ID,
    user_id: mockUser.id,
    team_name: 'Mobile Team',
    total_points: 42,
    users: { display_name: 'Test User' },
  },
  {
    id: OTHER_MEMBER_ID,
    user_id: OTHER_USER_ID,
    team_name: 'Opponent Mobile',
    total_points: 30,
    users: { display_name: 'Other Player' },
  },
];

// Mock players for draft page
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
];

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
];

const allPlayers = [...mockForwards, ...mockDefensemen];
const allTeams = [...mockTeams];

// Roster slots for roster page
const rosterSlots = [
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
    player_id: 8480069,
    team_id: null,
    position: 'D',
    is_active: true,
    points_earned: 3,
    activated_from_ir: false,
  },
  {
    id: 'slot-g1',
    league_member_id: MEMBER_ID,
    round: 1,
    player_id: null,
    team_id: 22,
    position: 'G',
    is_active: true,
    points_earned: 6,
    activated_from_ir: false,
  },
];

// Draft builder
function buildDraft(overrides: Record<string, unknown> = {}) {
  return {
    id: 'draft-mobile-0001',
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
// Route handler helpers
// ---------------------------------------------------------------------------
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

    if (method === 'PATCH') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(league),
      });
    }

    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([league]),
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
      body: JSON.stringify(membersListData),
    });
  };
}

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

    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(draft),
    });
  };
}

// ──────────────────────────────────────────────────────────────────────────────
// Mobile Viewport Tests
// ──────────────────────────────────────────────────────────────────────────────
test.describe('Mobile Viewport', () => {
  test('mobile viewport shows responsive navigation — user name hidden on small screens', async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.setViewportSize(MOBILE_VIEWPORT);
    await setupSupabaseMocks(authenticatedPage);
    await authenticatedPage.goto('/');

    const dashboard = new DashboardPage(authenticatedPage);
    await expect(dashboard.heading).toBeVisible(NAV_TIMEOUT);

    // App header should still be visible
    await expect(
      authenticatedPage.getByRole('link', { name: /sportsnot/i })
    ).toBeVisible();

    // On mobile, user display name is hidden (visibleFrom="sm") — only avatar initial shows
    // The user menu trigger should still be accessible via the avatar button
    const displayName = mockUser.user_metadata.display_name;
    const nameText = authenticatedPage
      .locator('header')
      .getByText(displayName, { exact: true });
    await expect(nameText).toBeHidden();

    // Avatar initial should still be visible and menu should work
    const menuTrigger = authenticatedPage.locator('header button').last();
    await menuTrigger.click();
    await expect(
      authenticatedPage.getByRole('menuitem', { name: /dashboard/i })
    ).toBeVisible();
    await expect(
      authenticatedPage.getByRole('menuitem', { name: /sign out/i })
    ).toBeVisible();
  });

  test('draft page is usable on mobile — scrolling, filtering, and picking work', async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.setViewportSize(MOBILE_VIEWPORT);

    const draft = buildDraft();

    await setupSupabaseMocks(authenticatedPage, {
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
          body: JSON.stringify([]),
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

    // Wait for Draft Room heading
    await expect(
      authenticatedPage.getByRole('heading', { name: /Draft Room/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Players should be visible
    await expect(authenticatedPage.getByText('Connor McDavid')).toBeVisible();

    // Filter by position — Mantine SegmentedControl works on mobile
    await authenticatedPage.locator('label:has-text("Defense")').click();
    await expect(authenticatedPage.getByText('Cale Makar')).toBeVisible();
    await expect(authenticatedPage.getByText('Connor McDavid')).toBeHidden();

    // Switch back to All
    await authenticatedPage.locator('label:has-text("All")').click();
    await expect(authenticatedPage.getByText('Connor McDavid')).toBeVisible();

    // Search works on mobile
    const searchInput = authenticatedPage.getByPlaceholder(/Search players/i);
    await searchInput.fill('Crosby');
    await expect(authenticatedPage.getByText('Sidney Crosby')).toBeVisible();
    await expect(authenticatedPage.getByText('Connor McDavid')).toBeHidden();
    await searchInput.clear();

    // Click Draft button — on mobile the table is a card layout (no rows)
    const playerCard = authenticatedPage
      .locator('[class*="Card"]')
      .filter({ hasText: 'Connor McDavid' });
    await playerCard.getByRole('button', { name: /Draft/i }).click();

    const modal = authenticatedPage.getByRole('dialog');
    await expect(modal).toBeVisible();
    await expect(modal.getByText(/Confirm Draft Pick/i)).toBeVisible();
    await expect(modal.getByRole('button', { name: /Cancel/i })).toBeVisible();
    await expect(
      modal.getByRole('button', { name: /Confirm Pick/i })
    ).toBeVisible();

    // Cancel the modal
    await modal.getByRole('button', { name: /Cancel/i }).click();
    await expect(modal).toBeHidden();
  });

  test('roster page renders correctly on mobile viewport', async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.setViewportSize(MOBILE_VIEWPORT);

    await setupSupabaseMocks(authenticatedPage, {
      leagues: leagueHandler(),
      league_members: leagueMembersHandler(),
      rosters: mockTableList(rosterSlots),
      player_stats_cache: mockTableList(allPlayers),
      team_stats_cache: mockTableList(allTeams),
    });

    await authenticatedPage.goto(`/roster/${LEAGUE_ID}`);

    // Wait for heading
    await expect(
      authenticatedPage.getByRole('heading', { name: /My Roster/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Position group headings should be visible
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

    // Total Points card should be visible
    await expect(authenticatedPage.getByText('Total Points')).toBeVisible();

    // Player entries should be visible with resolved names
    await expect(authenticatedPage.getByText('Connor McDavid')).toBeVisible();

    // Round info should be displayed
    await expect(
      authenticatedPage.getByText('Round 1', { exact: true })
    ).toBeVisible();
  });

  test('league dashboard is navigable on mobile', async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.setViewportSize(MOBILE_VIEWPORT);

    await setupSupabaseMocks(authenticatedPage, {
      leagues: leagueHandler(),
    });

    await authenticatedPage.goto(`/leagues/${LEAGUE_ID}`);

    // League name heading should be visible
    await expect(
      authenticatedPage.getByRole('heading', { name: /Mobile Test League/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Status badge should be visible
    await expect(authenticatedPage.getByText('active')).toBeVisible();

    // Members should be listed
    await expect(authenticatedPage.getByText('Mobile Team')).toBeVisible();
    await expect(authenticatedPage.getByText('Opponent Mobile')).toBeVisible();

    // Navigation buttons should be accessible on mobile
    // "My Roster" button should be visible for active league
    await expect(
      authenticatedPage.getByRole('button', { name: /My Roster/i })
    ).toBeVisible();

    // App header should still show logo
    await expect(
      authenticatedPage.getByRole('link', { name: /sportsnot/i })
    ).toBeVisible();
  });

  test('modals render correctly on mobile viewports', async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.setViewportSize(MOBILE_VIEWPORT);

    const draft = buildDraft();

    await setupSupabaseMocks(authenticatedPage, {
      leagues: leagueHandler(),
      league_members: mockTableList(membersListData),
      drafts: draftHandler(draft),
      draft_picks: async (route) => {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      },
      player_stats_cache: mockTableList(allPlayers),
      team_stats_cache: mockTableList(allTeams),
      rosters: async (route) => {
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

    // Open the draft confirmation modal — on mobile, cards replace rows
    const playerCard = authenticatedPage
      .locator('[class*="Card"]')
      .filter({ hasText: 'Connor McDavid' });
    await playerCard.getByRole('button', { name: /Draft/i }).click();

    const modal = authenticatedPage.getByRole('dialog');
    await expect(modal).toBeVisible();

    // Modal should be fully visible within the mobile viewport
    await expect(modal.getByText(/Confirm Draft Pick/i)).toBeVisible();
    await expect(modal.getByText(/Connor McDavid/i)).toBeVisible();

    // Buttons should be clickable — verify they're within viewport
    const confirmBtn = modal.getByRole('button', { name: /Confirm Pick/i });
    await expect(confirmBtn).toBeVisible();
    await expect(confirmBtn).toBeEnabled();

    const cancelBtn = modal.getByRole('button', { name: /Cancel/i });
    await expect(cancelBtn).toBeVisible();
    await expect(cancelBtn).toBeEnabled();

    // Close the modal via Cancel
    await cancelBtn.click();
    await expect(modal).toBeHidden();
  });
});
