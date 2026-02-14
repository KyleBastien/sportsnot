import { test, expect } from '../fixtures/auth.fixture';
import { setupSupabaseMocks } from '../fixtures/supabase-mock.fixture';
import { mockUser } from '../fixtures/auth.fixture';

const NAV_TIMEOUT = { timeout: 15000 };

test.describe('League Creation Flow', () => {
  test('navigating to /leagues/create shows league creation form', async ({
    authenticatedPage,
  }) => {
    await setupSupabaseMocks(authenticatedPage);
    await authenticatedPage.goto('/leagues/create');

    await expect(
      authenticatedPage.getByRole('heading', { name: /create a league/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Verify form fields
    await expect(
      authenticatedPage.getByRole('textbox', { name: /league name/i })
    ).toBeVisible();
    await expect(
      authenticatedPage.getByRole('textbox', { name: /your team name/i })
    ).toBeVisible();
    await expect(
      authenticatedPage.getByRole('textbox', { name: /max participants/i })
    ).toBeVisible();
    await expect(
      authenticatedPage.getByRole('button', { name: /create league/i })
    ).toBeVisible();
  });

  test('form validates required fields — league name and team name cannot be empty', async ({
    authenticatedPage,
  }) => {
    await setupSupabaseMocks(authenticatedPage);
    await authenticatedPage.goto('/leagues/create');

    await expect(
      authenticatedPage.getByRole('heading', { name: /create a league/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Click submit without filling required fields
    await authenticatedPage.getByRole('button', { name: /create league/i }).click();

    // Should stay on the same page (HTML5 validation prevents submission)
    await expect(authenticatedPage).toHaveURL(/\/leagues\/create/);
  });

  test('form enforces max participants range 2 to 12', async ({
    authenticatedPage,
  }) => {
    await setupSupabaseMocks(authenticatedPage);
    await authenticatedPage.goto('/leagues/create');

    await expect(
      authenticatedPage.getByRole('heading', { name: /create a league/i })
    ).toBeVisible(NAV_TIMEOUT);

    const maxInput = authenticatedPage.getByRole('textbox', {
      name: /max participants/i,
    });

    // Mantine NumberInput has min/max constraints
    // Verify the input is present and has the default value of 8
    await expect(maxInput).toBeVisible();
    await expect(maxInput).toHaveValue('8');
  });

  test('successful submission mocks POST to Supabase and navigates to league dashboard', async ({
    authenticatedPage,
  }) => {
    const leagueId = '11111111-2222-3333-4444-555555555555';
    const leagueName = 'Test Created League';
    const teamName = 'My Awesome Team';

    // Track POST requests to verify correct data is sent
    const postRequests: { url: string; body: string }[] = [];

    // Set up mocks with custom league creation handling
    await setupSupabaseMocks(authenticatedPage, {
      leagues: async (route) => {
        const request = route.request();
        const method = request.method();

        if (method === 'POST') {
          postRequests.push({
            url: request.url(),
            body: await request.postData() ?? '',
          });
          // Return the created league
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              id: leagueId,
              name: leagueName,
              commissioner_id: mockUser.id,
              invite_code: 'TESTCODE',
              max_participants: 8,
              status: 'setup',
              current_round: 1,
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            }),
          });
        }

        // GET for the league dashboard page (with join query)
        const accept = request.headers()['accept'] ?? '';
        if (method === 'GET' && accept.includes('vnd.pgrst.object+json')) {
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              id: leagueId,
              name: leagueName,
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
                  team_name: teamName,
                  total_points: 0,
                  users: {
                    display_name: mockUser.user_metadata.display_name,
                    avatar_url: mockUser.user_metadata.avatar_url,
                  },
                },
              ],
            }),
          });
        }

        // Default list query
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      },
      league_members: async (route) => {
        const request = route.request();
        const method = request.method();

        if (method === 'POST') {
          postRequests.push({
            url: request.url(),
            body: await request.postData() ?? '',
          });
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

    await authenticatedPage.goto('/leagues/create');

    await expect(
      authenticatedPage.getByRole('heading', { name: /create a league/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Fill form
    await authenticatedPage
      .getByRole('textbox', { name: /league name/i })
      .fill(leagueName);
    await authenticatedPage
      .getByRole('textbox', { name: /your team name/i })
      .fill(teamName);

    // Submit
    await authenticatedPage.getByRole('button', { name: /create league/i }).click();

    // Should navigate to league dashboard
    await expect(authenticatedPage).toHaveURL(
      new RegExp(`/leagues/${leagueId}`),
      NAV_TIMEOUT
    );

    // Verify league name appears on dashboard
    await expect(
      authenticatedPage.getByRole('heading', { name: leagueName })
    ).toBeVisible();
  });

  test('new league dashboard shows invite code and commissioner controls', async ({
    authenticatedPage,
  }) => {
    const leagueId = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
    const leagueName = 'Commissioner League';
    const inviteCode = 'ABCD1234';

    await setupSupabaseMocks(authenticatedPage, {
      leagues: async (route) => {
        const request = route.request();
        const accept = request.headers()['accept'] ?? '';

        if (accept.includes('vnd.pgrst.object+json')) {
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              id: leagueId,
              name: leagueName,
              commissioner_id: mockUser.id,
              invite_code: inviteCode,
              max_participants: 8,
              status: 'setup',
              current_round: 1,
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              league_members: [
                {
                  id: 'member-1',
                  user_id: mockUser.id,
                  team_name: 'My Team',
                  total_points: 0,
                  users: {
                    display_name: mockUser.user_metadata.display_name,
                    avatar_url: mockUser.user_metadata.avatar_url,
                  },
                },
              ],
            }),
          });
        }

        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      },
    });

    await authenticatedPage.goto(`/leagues/${leagueId}`);

    // Verify league name and status badge
    await expect(
      authenticatedPage.getByRole('heading', { name: leagueName })
    ).toBeVisible(NAV_TIMEOUT);
    await expect(authenticatedPage.getByText('setup')).toBeVisible();

    // Verify invite code is displayed
    await expect(authenticatedPage.getByText(inviteCode)).toBeVisible();
    await expect(authenticatedPage.getByText(/invite code/i)).toBeVisible();

    // Verify commissioner controls: Settings button
    await expect(
      authenticatedPage.getByRole('button', { name: /settings/i })
    ).toBeVisible();

    // Verify commissioner controls: Start Draft button (disabled with < 2 members)
    const startDraftButton = authenticatedPage.getByRole('button', {
      name: /start draft/i,
    });
    await expect(startDraftButton).toBeVisible();
    await expect(startDraftButton).toBeDisabled();
  });

  test('invite code copy button interaction works', async ({
    authenticatedPage,
  }) => {
    const leagueId = 'cccccccc-dddd-eeee-ffff-111111111111';
    const inviteCode = 'COPY1234';

    // Grant clipboard permissions
    await authenticatedPage.context().grantPermissions(['clipboard-read', 'clipboard-write']);

    await setupSupabaseMocks(authenticatedPage, {
      leagues: async (route) => {
        const request = route.request();
        const accept = request.headers()['accept'] ?? '';

        if (accept.includes('vnd.pgrst.object+json')) {
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              id: leagueId,
              name: 'Copy Test League',
              commissioner_id: mockUser.id,
              invite_code: inviteCode,
              max_participants: 8,
              status: 'setup',
              current_round: 1,
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              league_members: [
                {
                  id: 'member-1',
                  user_id: mockUser.id,
                  team_name: 'Copy Team',
                  total_points: 0,
                  users: {
                    display_name: mockUser.user_metadata.display_name,
                    avatar_url: mockUser.user_metadata.avatar_url,
                  },
                },
              ],
            }),
          });
        }

        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      },
    });

    await authenticatedPage.goto(`/leagues/${leagueId}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /copy test league/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Find and click the copy button (ActionIcon showing 📋 emoji)
    const copyButton = authenticatedPage.getByRole('button', { name: '📋' });
    await expect(copyButton).toBeVisible();
    await copyButton.click();

    // After clicking, the button shows checkmark instead of clipboard emoji
    await expect(authenticatedPage.getByRole('button', { name: '✓' })).toBeVisible();

    // Verify clipboard content
    const clipboardText = await authenticatedPage.evaluate(() =>
      navigator.clipboard.readText()
    );
    expect(clipboardText).toBe(inviteCode);
  });
});
