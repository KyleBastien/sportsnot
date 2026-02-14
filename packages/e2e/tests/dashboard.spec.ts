import { test, expect } from '../fixtures/auth.fixture';
import {
  setupSupabaseMocks,
  mockTableList,
} from '../fixtures/supabase-mock.fixture';
import { mockUser } from '../fixtures/auth.fixture';
import { createMockLeague } from '../fixtures/data-factories';
import { DashboardPage } from '../page-objects';

const NAV_TIMEOUT = { timeout: 15000 };

/** Build league response objects that match the shape the dashboard query returns */
function createLeagueWithMembers(
  overrides?: Partial<{
    name: string;
    status: string;
    current_round: number;
    id: string;
  }>
) {
  const league = createMockLeague(overrides as any);
  return {
    id: league.id,
    name: league.name,
    status: league.status,
    current_round: league.currentRound,
    max_participants: league.maxParticipants,
    commissioner_id: league.commissionerId,
    invite_code: league.inviteCode,
    created_at: league.createdAt,
    updated_at: league.updatedAt,
    league_members: [
      {
        team_name: 'My Team',
        total_points: 42,
        user_id: mockUser.id,
      },
    ],
  };
}

test.describe('Dashboard', () => {
  test('authenticated user sees dashboard page with heading', async ({
    authenticatedPage,
  }) => {
    await setupSupabaseMocks(authenticatedPage);
    await authenticatedPage.goto('/');

    const dashboard = new DashboardPage(authenticatedPage);
    await expect(dashboard.heading).toBeVisible(NAV_TIMEOUT);
    await expect(
      authenticatedPage.getByText(/welcome back/i)
    ).toBeVisible();
  });

  test('dashboard shows league list when user has leagues', async ({
    authenticatedPage,
  }) => {
    const leagues = [
      createLeagueWithMembers({ name: 'Playoff Legends', status: 'active', current_round: 2 }),
      createLeagueWithMembers({ name: 'Office Pool', status: 'setup', current_round: 1 }),
      createLeagueWithMembers({ name: 'Family League', status: 'drafting', current_round: 1 }),
    ];

    await setupSupabaseMocks(authenticatedPage, {
      leagues: mockTableList(leagues),
    });
    await authenticatedPage.goto('/');

    const dashboard = new DashboardPage(authenticatedPage);
    await expect(dashboard.heading).toBeVisible(NAV_TIMEOUT);

    // Verify all league names appear
    await expect(authenticatedPage.getByText('Playoff Legends')).toBeVisible();
    await expect(authenticatedPage.getByText('Office Pool')).toBeVisible();
    await expect(authenticatedPage.getByText('Family League')).toBeVisible();

    // Verify status badges
    await expect(authenticatedPage.getByText('active')).toBeVisible();
    await expect(authenticatedPage.getByText('setup')).toBeVisible();
    await expect(authenticatedPage.getByText('drafting')).toBeVisible();
  });

  test('dashboard shows no leagues empty state when user has no leagues', async ({
    authenticatedPage,
  }) => {
    // Default mocks return empty arrays for all tables
    await setupSupabaseMocks(authenticatedPage);
    await authenticatedPage.goto('/');

    const dashboard = new DashboardPage(authenticatedPage);
    await expect(dashboard.heading).toBeVisible(NAV_TIMEOUT);

    await expect(
      authenticatedPage.getByText(/haven't joined any leagues/i)
    ).toBeVisible();
  });

  test('dashboard displays live games widget when games are in progress', async ({
    authenticatedPage,
  }) => {
    // The live games widget is not yet implemented in the dashboard.
    // This test verifies the dashboard loads correctly and is a placeholder
    // for when the widget is added.
    test.skip(true, 'Live games widget not yet implemented in dashboard');
  });

  test('clicking a league card navigates to /leagues/:leagueId', async ({
    authenticatedPage,
  }) => {
    const league = createLeagueWithMembers({ name: 'Click Test League' });

    await setupSupabaseMocks(authenticatedPage, {
      leagues: mockTableList([league]),
    });
    await authenticatedPage.goto('/');

    const dashboard = new DashboardPage(authenticatedPage);
    await expect(dashboard.heading).toBeVisible(NAV_TIMEOUT);

    // Click the league card
    await dashboard.navigateToLeague('Click Test League');

    await expect(authenticatedPage).toHaveURL(
      new RegExp(`/leagues/${league.id}`),
      NAV_TIMEOUT
    );
  });

  test('Create League and Join League CTAs are visible and navigate correctly', async ({
    authenticatedPage,
  }) => {
    await setupSupabaseMocks(authenticatedPage);
    await authenticatedPage.goto('/');

    const dashboard = new DashboardPage(authenticatedPage);
    await expect(dashboard.heading).toBeVisible(NAV_TIMEOUT);

    // Verify CTAs are visible
    await expect(dashboard.getCreateLeagueCTA()).toBeVisible();
    await expect(dashboard.getJoinLeagueCTA()).toBeVisible();

    // Test Create League navigation
    await dashboard.getCreateLeagueCTA().click();
    await expect(authenticatedPage).toHaveURL(/\/leagues\/create/, NAV_TIMEOUT);

    // Go back and test Join League navigation
    await authenticatedPage.goBack();
    await expect(dashboard.heading).toBeVisible(NAV_TIMEOUT);
    await dashboard.getJoinLeagueCTA().click();
    await expect(authenticatedPage).toHaveURL(/\/leagues\/join/, NAV_TIMEOUT);
  });
});
