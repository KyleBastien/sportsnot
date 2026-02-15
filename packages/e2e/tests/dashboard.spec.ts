import { test, expect } from '../fixtures/auth.fixture';
import {
  setupSupabaseMocks,
  mockTableList,
} from '../fixtures/supabase-mock.fixture';
import { mockUser } from '../fixtures/auth.fixture';
import { createMockLeague } from '../fixtures/data-factories';
import { DashboardPage } from '../page-objects';
import type { League } from '@sportsnot/types';

const NAV_TIMEOUT = { timeout: 15000 };

/** Build league response objects that match the shape the dashboard query returns */
function createLeagueWithMembers(overrides?: Partial<League>) {
  const league = createMockLeague(overrides);
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
    await expect(authenticatedPage.getByText(/welcome back/i)).toBeVisible();
  });

  test('dashboard shows league list when user has leagues', async ({
    authenticatedPage,
  }) => {
    const leagues = [
      createLeagueWithMembers({
        name: 'Playoff Legends',
        status: 'active',
        currentRound: 2,
      }),
      createLeagueWithMembers({
        name: 'Office Pool',
        status: 'setup',
        currentRound: 1,
      }),
      createLeagueWithMembers({
        name: 'Family League',
        status: 'drafting',
        currentRound: 1,
      }),
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
    const liveTeams = [
      {
        team_id: 6,
        team_name: 'Boston Bruins',
        team_abbreviation: 'BOS',
        wins: 3,
        shutouts: 1,
        is_eliminated: false,
      },
      {
        team_id: 14,
        team_name: 'Tampa Bay Lightning',
        team_abbreviation: 'TBL',
        wins: 2,
        shutouts: 0,
        is_eliminated: false,
      },
    ];

    await setupSupabaseMocks(authenticatedPage, {
      team_stats_cache: mockTableList(liveTeams),
    });
    await authenticatedPage.goto('/');

    const dashboard = new DashboardPage(authenticatedPage);
    await expect(dashboard.heading).toBeVisible(NAV_TIMEOUT);

    // Live Games section should be visible
    await expect(
      authenticatedPage.getByRole('heading', { name: /Live Games/i })
    ).toBeVisible();

    // Both teams should appear
    await expect(authenticatedPage.getByText('Boston Bruins')).toBeVisible();
    await expect(
      authenticatedPage.getByText('Tampa Bay Lightning')
    ).toBeVisible();

    // Badge abbreviations
    await expect(
      authenticatedPage.getByText('BOS', { exact: true })
    ).toBeVisible();
    await expect(
      authenticatedPage.getByText('TBL', { exact: true })
    ).toBeVisible();
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
