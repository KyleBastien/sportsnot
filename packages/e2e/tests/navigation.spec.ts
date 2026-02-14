import { test, expect, mockUser } from '../fixtures/auth.fixture';
import {
  setupSupabaseMocks,
  mockTableData,
} from '../fixtures/supabase-mock.fixture';
import { createMockLeague } from '../fixtures/data-factories';
import { DashboardPage } from '../page-objects';

const NAV_TIMEOUT = { timeout: 15000 };

/** Build a minimal league mock that satisfies dashboard + league dashboard queries */
function createLeagueResponse(overrides?: Record<string, unknown>) {
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
        id: 'member-1',
        user_id: mockUser.id,
        team_name: 'My Team',
        total_points: 42,
        users: {
          display_name: mockUser.user_metadata.display_name,
          avatar_url: null,
        },
      },
    ],
  };
}

test.describe('Navigation and Routing', () => {
  test('main nav links navigate to the correct pages', async ({
    authenticatedPage,
  }) => {
    await setupSupabaseMocks(authenticatedPage);
    await authenticatedPage.goto('/');

    // Wait for dashboard to load
    const dashboard = new DashboardPage(authenticatedPage);
    await expect(dashboard.heading).toBeVisible(NAV_TIMEOUT);

    // Open user menu and navigate to Profile
    const displayName = mockUser.user_metadata.display_name;
    const menuTrigger = authenticatedPage.getByRole('button').filter({
      has: authenticatedPage.getByText(displayName),
    });
    const triggerCount = await menuTrigger.count();
    if (triggerCount > 0) {
      await menuTrigger.first().click();
    } else {
      await authenticatedPage
        .locator('header button')
        .filter({ hasText: displayName[0].toUpperCase() })
        .click();
    }
    await authenticatedPage
      .getByRole('menuitem', { name: /profile/i })
      .click();
    await expect(authenticatedPage).toHaveURL(/\/profile/, NAV_TIMEOUT);

    // Navigate to Dashboard via user menu
    const menuTrigger2 = authenticatedPage.getByRole('button').filter({
      has: authenticatedPage.getByText(displayName),
    });
    const trigger2Count = await menuTrigger2.count();
    if (trigger2Count > 0) {
      await menuTrigger2.first().click();
    } else {
      await authenticatedPage
        .locator('header button')
        .filter({ hasText: displayName[0].toUpperCase() })
        .click();
    }
    await authenticatedPage
      .getByRole('menuitem', { name: /dashboard/i })
      .click();
    await expect(authenticatedPage).toHaveURL(
      /^http:\/\/localhost:\d+\/?$/,
      NAV_TIMEOUT
    );

    // Navigate via logo/home link
    await authenticatedPage.goto('/profile');
    await expect(authenticatedPage).toHaveURL(/\/profile/, NAV_TIMEOUT);
    await authenticatedPage
      .getByRole('heading', { name: /sportsnot/i })
      .click();
    await expect(authenticatedPage).toHaveURL(
      /^http:\/\/localhost:\d+\/?$/,
      NAV_TIMEOUT
    );
  });

  test('browser back and forward navigation works correctly', async ({
    authenticatedPage,
  }) => {
    await setupSupabaseMocks(authenticatedPage);

    // Navigate: Dashboard → Create League → Join League
    await authenticatedPage.goto('/');
    const dashboard = new DashboardPage(authenticatedPage);
    await expect(dashboard.heading).toBeVisible(NAV_TIMEOUT);

    await authenticatedPage.goto('/leagues/create');
    await expect(authenticatedPage).toHaveURL(/\/leagues\/create/, NAV_TIMEOUT);

    await authenticatedPage.goto('/leagues/join');
    await expect(authenticatedPage).toHaveURL(/\/leagues\/join/, NAV_TIMEOUT);

    // Go back to Create League
    await authenticatedPage.goBack();
    await expect(authenticatedPage).toHaveURL(/\/leagues\/create/, NAV_TIMEOUT);

    // Go back to Dashboard
    await authenticatedPage.goBack();
    await expect(authenticatedPage).toHaveURL(
      /^http:\/\/localhost:\d+\/?$/,
      NAV_TIMEOUT
    );
    await expect(dashboard.heading).toBeVisible(NAV_TIMEOUT);

    // Go forward to Create League
    await authenticatedPage.goForward();
    await expect(authenticatedPage).toHaveURL(/\/leagues\/create/, NAV_TIMEOUT);

    // Go forward to Join League
    await authenticatedPage.goForward();
    await expect(authenticatedPage).toHaveURL(/\/leagues\/join/, NAV_TIMEOUT);
  });

  test('deep-linking to any protected route redirects to /auth/login when unauthenticated', async ({
    unauthenticatedPage,
  }) => {
    await setupSupabaseMocks(unauthenticatedPage);

    const protectedRoutes = [
      '/',
      '/profile',
      '/leagues/create',
      '/leagues/join',
      '/leagues/some-league-id',
      '/leagues/some-league-id/settings',
      '/draft/some-league-id/lobby',
      '/draft/some-league-id',
      '/draft/some-league-id/transition',
      '/roster/some-league-id',
      '/roster/some-league-id/history',
      '/standings/some-league-id',
    ];

    for (const route of protectedRoutes) {
      await unauthenticatedPage.goto(route);
      await expect(unauthenticatedPage).toHaveURL(
        /\/auth\/login/,
        NAV_TIMEOUT
      );
    }
  });

  test('deep-linking to a valid route when authenticated loads the correct page', async ({
    authenticatedPage,
  }) => {
    const league = createLeagueResponse({
      name: 'Deep Link League',
      status: 'active',
    });

    await setupSupabaseMocks(authenticatedPage, {
      leagues: mockTableData(
        [league],
        league
      ),
    });
    // Deep-link to profile
    await authenticatedPage.goto('/profile');
    await expect(authenticatedPage).toHaveURL(/\/profile/, NAV_TIMEOUT);
    await expect(
      authenticatedPage.getByRole('heading', { name: /profile/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Deep-link to create league
    await authenticatedPage.goto('/leagues/create');
    await expect(authenticatedPage).toHaveURL(/\/leagues\/create/, NAV_TIMEOUT);
    await expect(
      authenticatedPage.getByRole('heading', { name: /create.*league/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Deep-link to join league
    await authenticatedPage.goto('/leagues/join');
    await expect(authenticatedPage).toHaveURL(/\/leagues\/join/, NAV_TIMEOUT);
    await expect(
      authenticatedPage.getByRole('heading', { name: /join.*league/i })
    ).toBeVisible(NAV_TIMEOUT);
  });

  test('unknown routes show 404 error page or redirect to dashboard', async ({
    authenticatedPage,
  }) => {
    await setupSupabaseMocks(authenticatedPage);

    // Navigate to a route that doesn't exist
    await authenticatedPage.goto('/this-route-does-not-exist');
    await authenticatedPage.waitForLoadState('networkidle');

    // Since no catch-all route is defined, the page will either:
    // 1. Show a 404 message, OR
    // 2. Render blank (no matching route) with just the header
    // Verify that the app shell header is still rendered (app didn't crash)
    await expect(
      authenticatedPage.getByRole('heading', { name: /sportsnot/i })
    ).toBeVisible(NAV_TIMEOUT);

    // The main content area should be empty (no route matched) or show error
    // Verify the page is NOT the dashboard (no "Dashboard" heading)
    await expect(
      authenticatedPage.getByRole('heading', { name: /^Dashboard$/i })
    ).not.toBeVisible();

    // Also test a nested unknown route
    await authenticatedPage.goto('/leagues/unknown-id/nonexistent-page');
    await authenticatedPage.waitForLoadState('networkidle');
    await expect(
      authenticatedPage.getByRole('heading', { name: /sportsnot/i })
    ).toBeVisible(NAV_TIMEOUT);
  });
});
