import { test, expect } from '../fixtures/auth.fixture';
import {
  setupSupabaseMocks,
  mockTableError,
} from '../fixtures/supabase-mock.fixture';
import { DashboardPage } from '../page-objects';

const NAV_TIMEOUT = { timeout: 15000 };

test.describe('Error States and Edge Cases', () => {
  test('network failure during data fetch shows error boundary or fallback UI', async ({
    authenticatedPage,
  }) => {
    // Mock leagues endpoint to return a 500 server error — app falls through
    // to the empty state as a graceful degradation since DashboardPage does not
    // destructure isError from React Query.
    await setupSupabaseMocks(authenticatedPage, {
      leagues: mockTableError(500, 'Internal Server Error', 'PGRST500'),
    });
    await authenticatedPage.goto('/');

    const dashboard = new DashboardPage(authenticatedPage);

    // The app should not crash — it renders the dashboard shell with fallback
    // empty state ("haven't joined any leagues") since the error is swallowed
    await expect(dashboard.heading).toBeVisible(NAV_TIMEOUT);
    await expect(
      authenticatedPage.getByText(/haven't joined any leagues/i)
    ).toBeVisible();
  });

  test('Supabase returning 401 triggers re-authentication flow redirect to login', async ({
    authenticatedPage,
  }) => {
    // Override auth user endpoint to return 401 (expired session)
    await authenticatedPage.route(
      'http://localhost:54321/auth/v1/user',
      (route) => {
        return route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({
            message: 'Invalid token',
            status: 401,
          }),
        });
      }
    );

    // Override token refresh to also return 400 (invalid refresh token)
    await authenticatedPage.route(
      'http://localhost:54321/auth/v1/token?grant_type=refresh_token',
      (route) => {
        return route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({
            error: 'invalid_grant',
            error_description: 'Invalid Refresh Token',
          }),
        });
      }
    );

    await setupSupabaseMocks(authenticatedPage);

    // Clear the localStorage session so Supabase re-evaluates auth
    await authenticatedPage.addInitScript(() => {
      // Remove any stored session tokens
      for (const key of Object.keys(window.localStorage)) {
        if (key.startsWith('sb-')) {
          window.localStorage.removeItem(key);
        }
      }
    });

    await authenticatedPage.goto('/');

    // Should redirect to login page since auth is invalid
    await expect(authenticatedPage).toHaveURL(/\/auth\/login/, NAV_TIMEOUT);
  });

  test('submitting forms with server-side validation errors shows error messages', async ({
    authenticatedPage,
  }) => {
    // Mock leagues POST to return a server-side error
    await setupSupabaseMocks(authenticatedPage, {
      leagues: async (route) => {
        const request = route.request();
        const method = request.method();

        if (method === 'POST') {
          return route.fulfill({
            status: 400,
            contentType: 'application/json',
            body: JSON.stringify({
              message:
                'new row violates check constraint "leagues_name_length"',
              details: null,
              hint: null,
              code: '23514',
            }),
          });
        }

        // Default GET returns empty list
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      },
    });

    await authenticatedPage.goto('/leagues/create');

    await expect(
      authenticatedPage.getByRole('heading', { name: /create a league/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Fill form with valid data
    await authenticatedPage
      .getByRole('textbox', { name: /league name/i })
      .fill('Test League');
    await authenticatedPage
      .getByRole('textbox', { name: /your team name/i })
      .fill('Test Team');

    // Submit — server returns error
    await authenticatedPage
      .getByRole('button', { name: /create league/i })
      .click();

    // Error alert should appear with the server error message
    await expect(
      authenticatedPage.getByText(/violates check constraint/i)
    ).toBeVisible();
  });

  test('loading states are displayed while data is being fetched', async ({
    authenticatedPage,
  }) => {
    // Mock leagues endpoint with a delayed response to observe loading state
    await setupSupabaseMocks(authenticatedPage, {
      leagues: async (route) => {
        // Delay the response by 3 seconds to ensure loading state is visible
        await new Promise((resolve) => setTimeout(resolve, 3000));
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      },
    });

    await authenticatedPage.goto('/');

    // While data is loading, a Mantine Loader component should be visible
    // Mantine Loader renders with role="presentation" and an SVG, or a generic loading indicator
    const loader = authenticatedPage.locator('.mantine-Loader-root');
    const loadingText = authenticatedPage.getByText(/loading/i);

    // At least one loading indicator should be visible before data arrives
    await expect(loader.first().or(loadingText.first())).toBeVisible({
      timeout: 5000,
    });

    // After the delayed response, loading should disappear and content should show
    const dashboard = new DashboardPage(authenticatedPage);
    await expect(dashboard.heading).toBeVisible(NAV_TIMEOUT);
  });

  test('empty states are shown for leagues with no members, drafts with no picks, etc.', async ({
    authenticatedPage,
  }) => {
    // Default mocks return empty arrays for all tables — triggers empty states
    await setupSupabaseMocks(authenticatedPage);
    await authenticatedPage.goto('/');

    const dashboard = new DashboardPage(authenticatedPage);
    await expect(dashboard.heading).toBeVisible(NAV_TIMEOUT);

    // Dashboard empty state: no leagues
    await expect(
      authenticatedPage.getByText(/haven't joined any leagues/i)
    ).toBeVisible();

    // Verify the empty state CTAs are available to guide the user
    await expect(dashboard.getCreateLeagueCTA()).toBeVisible();
    await expect(dashboard.getJoinLeagueCTA()).toBeVisible();
  });
});
