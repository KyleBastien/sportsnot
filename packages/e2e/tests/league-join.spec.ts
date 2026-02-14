import { test, expect } from '../fixtures/auth.fixture';
import { setupSupabaseMocks } from '../fixtures/supabase-mock.fixture';
import { mockUser } from '../fixtures/auth.fixture';

const NAV_TIMEOUT = { timeout: 15000 };

test.describe('Join League Flow', () => {
  test('navigating to /leagues/join shows invite code input field', async ({
    authenticatedPage,
  }) => {
    await setupSupabaseMocks(authenticatedPage);
    await authenticatedPage.goto('/leagues/join');

    await expect(
      authenticatedPage.getByRole('heading', { name: /join a league/i })
    ).toBeVisible(NAV_TIMEOUT);

    await expect(
      authenticatedPage.getByRole('textbox', { name: /invite code/i })
    ).toBeVisible();
    await expect(
      authenticatedPage.getByRole('button', { name: /find league/i })
    ).toBeVisible();
  });

  test('entering invalid invite code shows error message', async ({
    authenticatedPage,
  }) => {
    await setupSupabaseMocks(authenticatedPage, {
      // Default leagues mock returns 406 for .single() — simulates "not found"
    });
    await authenticatedPage.goto('/leagues/join');

    await expect(
      authenticatedPage.getByRole('heading', { name: /join a league/i })
    ).toBeVisible(NAV_TIMEOUT);

    await authenticatedPage
      .getByRole('textbox', { name: /invite code/i })
      .fill('BADCODE1');
    await authenticatedPage
      .getByRole('button', { name: /find league/i })
      .click();

    await expect(
      authenticatedPage.getByText(/league not found/i)
    ).toBeVisible();
  });

  test('entering valid invite code shows league preview and team name prompt', async ({
    authenticatedPage,
  }) => {
    const leagueId = '11111111-aaaa-bbbb-cccc-dddddddddddd';
    const leagueName = 'Valid Test League';

    await setupSupabaseMocks(authenticatedPage, {
      leagues: async (route) => {
        const request = route.request();
        const accept = request.headers()['accept'] ?? '';

        if (
          request.method() === 'GET' &&
          accept.includes('vnd.pgrst.object+json')
        ) {
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              id: leagueId,
              name: leagueName,
              max_participants: 8,
              league_members: [
                { id: 'existing-member-1' },
                { id: 'existing-member-2' },
                { id: 'existing-member-3' },
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

    await authenticatedPage.goto('/leagues/join');

    await expect(
      authenticatedPage.getByRole('heading', { name: /join a league/i })
    ).toBeVisible(NAV_TIMEOUT);

    await authenticatedPage
      .getByRole('textbox', { name: /invite code/i })
      .fill('VALIDCODE');
    await authenticatedPage
      .getByRole('button', { name: /find league/i })
      .click();

    // League preview shows name and member count
    await expect(authenticatedPage.getByText(leagueName)).toBeVisible();
    await expect(authenticatedPage.getByText(/3 \/ 8 members/i)).toBeVisible();

    // Team name input appears
    await expect(
      authenticatedPage.getByRole('textbox', { name: /your team name/i })
    ).toBeVisible();
    await expect(
      authenticatedPage.getByRole('button', { name: /join league/i })
    ).toBeVisible();
  });

  test('submitting team name joins league and navigates to league dashboard', async ({
    authenticatedPage,
  }) => {
    const leagueId = '22222222-aaaa-bbbb-cccc-dddddddddddd';
    const leagueName = 'Joinable League';
    const teamName = 'My New Team';

    await setupSupabaseMocks(authenticatedPage, {
      leagues: async (route) => {
        const request = route.request();
        const accept = request.headers()['accept'] ?? '';

        if (
          request.method() === 'GET' &&
          accept.includes('vnd.pgrst.object+json')
        ) {
          // Check if this is the join-page lookup (has league_members(id) select)
          // or the league dashboard query (has full league_members select with users)
          const url = request.url();
          if (url.includes('league_members(id)')) {
            // Lookup query from JoinLeaguePage
            return route.fulfill({
              status: 200,
              contentType: 'application/json',
              body: JSON.stringify({
                id: leagueId,
                name: leagueName,
                max_participants: 8,
                league_members: [{ id: 'existing-member-1' }],
              }),
            });
          }
          // League dashboard query with full member details
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              id: leagueId,
              name: leagueName,
              commissioner_id: 'other-user-id',
              invite_code: 'JOINCODE',
              max_participants: 8,
              status: 'setup',
              current_round: 1,
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              league_members: [
                {
                  id: 'existing-member-1',
                  user_id: 'other-user-id',
                  team_name: 'Other Team',
                  total_points: 0,
                  users: {
                    display_name: 'Other User',
                    avatar_url: 'https://example.com/other.png',
                  },
                },
                {
                  id: 'new-member-1',
                  user_id: mockUser.id,
                  team_name: teamName,
                  total_points: 0,
                  users: {
                    display_name:
                      mockUser.user_metadata.display_name,
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
      league_members: async (route) => {
        const request = route.request();
        if (request.method() === 'POST') {
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

    await authenticatedPage.goto('/leagues/join');

    await expect(
      authenticatedPage.getByRole('heading', { name: /join a league/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Step 1: Enter invite code
    await authenticatedPage
      .getByRole('textbox', { name: /invite code/i })
      .fill('JOINCODE');
    await authenticatedPage
      .getByRole('button', { name: /find league/i })
      .click();

    // Wait for preview
    await expect(authenticatedPage.getByText(leagueName)).toBeVisible();

    // Step 2: Enter team name and submit
    await authenticatedPage
      .getByRole('textbox', { name: /your team name/i })
      .fill(teamName);
    await authenticatedPage
      .getByRole('button', { name: /join league/i })
      .click();

    // Should navigate to league dashboard
    await expect(authenticatedPage).toHaveURL(
      new RegExp(`/leagues/${leagueId}`),
      NAV_TIMEOUT
    );

    await expect(
      authenticatedPage.getByRole('heading', { name: leagueName })
    ).toBeVisible();
  });

  test('attempting to join a full league shows full league error', async ({
    authenticatedPage,
  }) => {
    const leagueId = '33333333-aaaa-bbbb-cccc-dddddddddddd';

    await setupSupabaseMocks(authenticatedPage, {
      leagues: async (route) => {
        const request = route.request();
        const accept = request.headers()['accept'] ?? '';

        if (
          request.method() === 'GET' &&
          accept.includes('vnd.pgrst.object+json')
        ) {
          // League is full: 4 members, max 4
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              id: leagueId,
              name: 'Full League',
              max_participants: 4,
              league_members: [
                { id: 'm1' },
                { id: 'm2' },
                { id: 'm3' },
                { id: 'm4' },
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

    await authenticatedPage.goto('/leagues/join');

    await expect(
      authenticatedPage.getByRole('heading', { name: /join a league/i })
    ).toBeVisible(NAV_TIMEOUT);

    await authenticatedPage
      .getByRole('textbox', { name: /invite code/i })
      .fill('FULLCODE');
    await authenticatedPage
      .getByRole('button', { name: /find league/i })
      .click();

    await expect(
      authenticatedPage.getByText(/this league is full/i)
    ).toBeVisible();
  });

  test('attempting to join an already-joined league shows already a member message', async ({
    authenticatedPage,
  }) => {
    const leagueId = '44444444-aaaa-bbbb-cccc-dddddddddddd';
    const leagueName = 'Already Joined League';

    await setupSupabaseMocks(authenticatedPage, {
      leagues: async (route) => {
        const request = route.request();
        const accept = request.headers()['accept'] ?? '';

        if (
          request.method() === 'GET' &&
          accept.includes('vnd.pgrst.object+json')
        ) {
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              id: leagueId,
              name: leagueName,
              max_participants: 8,
              league_members: [{ id: 'existing-member-1' }],
            }),
          });
        }

        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      },
      league_members: async (route) => {
        const request = route.request();
        if (request.method() === 'POST') {
          // Simulate unique constraint violation
          return route.fulfill({
            status: 409,
            contentType: 'application/json',
            body: JSON.stringify({
              message:
                'duplicate key value violates unique constraint "league_members_league_id_user_id_key"',
              details: null,
              hint: null,
              code: '23505',
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

    await authenticatedPage.goto('/leagues/join');

    await expect(
      authenticatedPage.getByRole('heading', { name: /join a league/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Step 1: Enter invite code
    await authenticatedPage
      .getByRole('textbox', { name: /invite code/i })
      .fill('DUPETEST');
    await authenticatedPage
      .getByRole('button', { name: /find league/i })
      .click();

    // Wait for preview
    await expect(authenticatedPage.getByText(leagueName)).toBeVisible();

    // Step 2: Enter team name and submit
    await authenticatedPage
      .getByRole('textbox', { name: /your team name/i })
      .fill('Duplicate Team');
    await authenticatedPage
      .getByRole('button', { name: /join league/i })
      .click();

    // Should show "already a member" error
    await expect(
      authenticatedPage.getByText(/already a member/i)
    ).toBeVisible();
  });
});
