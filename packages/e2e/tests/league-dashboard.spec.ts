import { test, expect } from '../fixtures/auth.fixture';
import { setupSupabaseMocks } from '../fixtures/supabase-mock.fixture';
import { mockUser } from '../fixtures/auth.fixture';

const NAV_TIMEOUT = { timeout: 15000 };
const LEAGUE_ID = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
const OTHER_USER_ID = '99999999-8888-7777-6666-555555555555';

/** Build a league payload with nested league_members for PostgREST `.single()` join */
function buildLeague(overrides: Record<string, unknown> = {}) {
  return {
    id: LEAGUE_ID,
    name: 'Test League',
    commissioner_id: mockUser.id,
    invite_code: 'TESTCODE',
    max_participants: 8,
    status: 'setup',
    current_round: 1,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    league_members: [
      {
        id: 'member-1',
        user_id: mockUser.id,
        team_name: 'Alpha Team',
        total_points: 25,
        users: {
          display_name: mockUser.user_metadata.display_name,
          avatar_url: mockUser.user_metadata.avatar_url,
        },
      },
      {
        id: 'member-2',
        user_id: OTHER_USER_ID,
        team_name: 'Beta Team',
        total_points: 30,
        users: {
          display_name: 'Other Player',
          avatar_url: 'https://example.com/other.png',
        },
      },
      {
        id: 'member-3',
        user_id: '77777777-6666-5555-4444-333333333333',
        team_name: 'Gamma Team',
        total_points: 18,
        users: {
          display_name: 'Third Player',
          avatar_url: 'https://example.com/third.png',
        },
      },
    ],
    ...overrides,
  };
}

/** Route handler that returns a league object for both list and `.single()` queries */
function leagueHandler(league: ReturnType<typeof buildLeague>) {
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
      body: JSON.stringify([]),
    });
  };
}

// ──────────────────────────────────────────────────────────────────────────────
// League Dashboard Tests
// ──────────────────────────────────────────────────────────────────────────────
test.describe('League Dashboard', () => {
  test('league dashboard shows league name, status, member list, and standings', async ({
    authenticatedPage,
  }) => {
    const league = buildLeague();
    await setupSupabaseMocks(authenticatedPage, {
      leagues: leagueHandler(league),
    });

    await authenticatedPage.goto(`/leagues/${LEAGUE_ID}`);

    // League name
    await expect(
      authenticatedPage.getByRole('heading', { name: 'Test League' })
    ).toBeVisible(NAV_TIMEOUT);

    // Status badge
    await expect(authenticatedPage.getByText('setup')).toBeVisible();

    // Member count
    await expect(
      authenticatedPage.getByText(/3\s*\/\s*8 members/)
    ).toBeVisible();

    // Standings heading
    await expect(
      authenticatedPage.getByRole('heading', { name: /standings/i })
    ).toBeVisible();

    // All three members appear in the table
    await expect(authenticatedPage.getByText('Alpha Team')).toBeVisible();
    await expect(authenticatedPage.getByText('Beta Team')).toBeVisible();
    await expect(authenticatedPage.getByText('Gamma Team')).toBeVisible();

    // Points are displayed
    await expect(authenticatedPage.getByText('25')).toBeVisible();
    await expect(authenticatedPage.getByText('30')).toBeVisible();
    await expect(authenticatedPage.getByText('18')).toBeVisible();
  });

  test('non-commissioner user sees no settings controls', async ({
    authenticatedPage,
  }) => {
    // commissioner_id is someone else, so current user is NOT commissioner
    const league = buildLeague({ commissioner_id: OTHER_USER_ID });
    await setupSupabaseMocks(authenticatedPage, {
      leagues: leagueHandler(league),
    });

    await authenticatedPage.goto(`/leagues/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: 'Test League' })
    ).toBeVisible(NAV_TIMEOUT);

    // Settings button should NOT be visible
    await expect(
      authenticatedPage.getByRole('button', { name: /settings/i })
    ).toBeHidden();

    // Start Draft button should NOT be visible (not commissioner)
    await expect(
      authenticatedPage.getByRole('button', { name: /start draft/i })
    ).toBeHidden();
  });

  test('commissioner sees settings link and can navigate to settings page', async ({
    authenticatedPage,
  }) => {
    const league = buildLeague();
    await setupSupabaseMocks(authenticatedPage, {
      leagues: leagueHandler(league),
    });

    await authenticatedPage.goto(`/leagues/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: 'Test League' })
    ).toBeVisible(NAV_TIMEOUT);

    // Settings button should be visible for commissioner
    const settingsButton = authenticatedPage.getByRole('button', {
      name: /settings/i,
    });
    await expect(settingsButton).toBeVisible();

    // Click settings to navigate
    await settingsButton.click();

    await expect(authenticatedPage).toHaveURL(
      new RegExp(`/leagues/${LEAGUE_ID}/settings`),
      NAV_TIMEOUT
    );

    // Settings page should show heading
    await expect(
      authenticatedPage.getByRole('heading', { name: /league settings/i })
    ).toBeVisible(NAV_TIMEOUT);
  });

  test('commissioner can edit league name from settings (mock PATCH request)', async ({
    authenticatedPage,
  }) => {
    const league = buildLeague();
    const patchRequests: string[] = [];

    await setupSupabaseMocks(authenticatedPage, {
      leagues: async (route) => {
        const request = route.request();
        const method = request.method();
        const accept = request.headers()['accept'] ?? '';

        if (method === 'PATCH') {
          patchRequests.push((await request.postData()) ?? '');
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({}),
          });
        }

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
      },
    });

    await authenticatedPage.goto(`/leagues/${LEAGUE_ID}/settings`);

    // Wait for settings page to load
    await expect(
      authenticatedPage.getByRole('heading', { name: /league settings/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Edit league name
    const nameInput = authenticatedPage.getByRole('textbox', {
      name: /league name/i,
    });
    await expect(nameInput).toBeVisible();
    await nameInput.clear();
    await nameInput.fill('Updated League Name');

    // Save
    await authenticatedPage
      .getByRole('button', { name: /save changes/i })
      .click();

    // Should show success alert
    await expect(authenticatedPage.getByText(/settings saved/i)).toBeVisible(
      NAV_TIMEOUT
    );

    // Verify PATCH was sent
    expect(patchRequests.length).toBeGreaterThan(0);
    expect(patchRequests[0]).toContain('Updated League Name');
  });

  test('commissioner can regenerate invite code', async ({
    authenticatedPage,
  }) => {
    const league = buildLeague();
    let patchCount = 0;

    await setupSupabaseMocks(authenticatedPage, {
      leagues: async (route) => {
        const request = route.request();
        const method = request.method();
        const accept = request.headers()['accept'] ?? '';

        if (method === 'PATCH') {
          patchCount++;
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({}),
          });
        }

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
      },
    });

    await authenticatedPage.goto(`/leagues/${LEAGUE_ID}/settings`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /league settings/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Verify current invite code is displayed
    await expect(authenticatedPage.getByText('TESTCODE')).toBeVisible();

    // Click regenerate button
    await authenticatedPage
      .getByRole('button', { name: /regenerate code/i })
      .click();

    // Success message should appear
    await expect(
      authenticatedPage.getByText(/invite code regenerated/i)
    ).toBeVisible(NAV_TIMEOUT);

    // Verify PATCH was issued
    expect(patchCount).toBeGreaterThan(0);
  });

  test('Start Draft button appears for commissioner when league status is setup', async ({
    authenticatedPage,
  }) => {
    const league = buildLeague({ status: 'setup' });
    await setupSupabaseMocks(authenticatedPage, {
      leagues: leagueHandler(league),
    });

    await authenticatedPage.goto(`/leagues/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: 'Test League' })
    ).toBeVisible(NAV_TIMEOUT);

    // Start Draft button visible for commissioner in setup status
    const startDraftButton = authenticatedPage.getByRole('button', {
      name: /start draft/i,
    });
    await expect(startDraftButton).toBeVisible();

    // Button should be enabled because there are 3 members (≥ 2)
    await expect(startDraftButton).toBeEnabled();
  });
});
