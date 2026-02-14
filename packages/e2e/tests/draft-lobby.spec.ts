import { test, expect } from '../fixtures/auth.fixture';
import { setupSupabaseMocks } from '../fixtures/supabase-mock.fixture';
import { mockUser } from '../fixtures/auth.fixture';

const NAV_TIMEOUT = { timeout: 15000 };
const LEAGUE_ID = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
const OTHER_USER_ID = '99999999-8888-7777-6666-555555555555';
const THIRD_USER_ID = '77777777-6666-5555-4444-333333333333';

/** Build a league payload with nested league_members for PostgREST `.single()` join */
function buildLeague(overrides: Record<string, unknown> = {}) {
  return {
    id: LEAGUE_ID,
    name: 'Playoff League Alpha',
    commissioner_id: mockUser.id,
    invite_code: 'LOBBY01',
    max_participants: 8,
    status: 'setup',
    current_round: 0,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    league_members: [
      {
        id: 'member-1',
        user_id: mockUser.id,
        team_name: 'Alpha Team',
        users: { display_name: mockUser.user_metadata.display_name },
      },
      {
        id: 'member-2',
        user_id: OTHER_USER_ID,
        team_name: 'Beta Team',
        users: { display_name: 'Other Player' },
      },
      {
        id: 'member-3',
        user_id: THIRD_USER_ID,
        team_name: 'Gamma Team',
        users: { display_name: 'Third Player' },
      },
    ],
    ...overrides,
  };
}

/** Route handler for leagues table — returns league for `.single()` and empty list for list queries */
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
// Draft Lobby Tests
// ──────────────────────────────────────────────────────────────────────────────
test.describe('Draft Lobby', () => {
  test('navigating to /draft/:leagueId/lobby shows member list with ready status', async ({
    authenticatedPage,
  }) => {
    const league = buildLeague();
    await setupSupabaseMocks(authenticatedPage, {
      leagues: leagueHandler(league),
    });

    await authenticatedPage.goto(`/draft/${LEAGUE_ID}/lobby`);

    // Heading
    await expect(
      authenticatedPage.getByRole('heading', { name: /Draft Lobby/i })
    ).toBeVisible(NAV_TIMEOUT);

    // League name and round info
    await expect(
      authenticatedPage.getByText(/Playoff League Alpha/)
    ).toBeVisible();
    await expect(
      authenticatedPage.getByText(/Playoff League Alpha — Round 1/)
    ).toBeVisible();

    // All three members are listed
    const memberList = authenticatedPage.getByRole('list');
    await expect(
      memberList.getByText(mockUser.user_metadata.display_name)
    ).toBeVisible();
    await expect(memberList.getByText('Other Player')).toBeVisible();
    await expect(memberList.getByText('Third Player')).toBeVisible();

    // Team names visible
    await expect(memberList.getByText('Alpha Team')).toBeVisible();
    await expect(memberList.getByText('Beta Team')).toBeVisible();
    await expect(memberList.getByText('Gamma Team')).toBeVisible();

    // Commissioner badge on the commissioner member
    await expect(authenticatedPage.getByText('Commissioner')).toBeVisible();

    // "You" badge on the current user
    await expect(authenticatedPage.getByText('You')).toBeVisible();
  });

  test('draft order snake visualization is displayed correctly', async ({
    authenticatedPage,
  }) => {
    const league = buildLeague();
    await setupSupabaseMocks(authenticatedPage, {
      leagues: leagueHandler(league),
    });

    await authenticatedPage.goto(`/draft/${LEAGUE_ID}/lobby`);

    // Wait for page to load
    await expect(
      authenticatedPage.getByRole('heading', { name: /Draft Lobby/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Draft Info card shows Snake Draft format
    await expect(authenticatedPage.getByText('Snake Draft')).toBeVisible();

    // Participants count
    await expect(
      authenticatedPage.getByText('3', { exact: true })
    ).toBeVisible();

    // Total picks: 3 members × 11 picks = 33
    await expect(
      authenticatedPage.getByText('33', { exact: true })
    ).toBeVisible();

    // Roster config
    await expect(
      authenticatedPage.getByText('5F, 3D, 1G, 1IR_F, 1IR_D')
    ).toBeVisible();
  });

  test('commissioner sees Start Draft button in lobby', async ({
    authenticatedPage,
  }) => {
    const league = buildLeague(); // commissioner_id = mockUser.id
    await setupSupabaseMocks(authenticatedPage, {
      leagues: leagueHandler(league),
    });

    await authenticatedPage.goto(`/draft/${LEAGUE_ID}/lobby`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /Draft Lobby/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Start Draft button should be visible and enabled (3 members ≥ 2)
    const startButton = authenticatedPage.getByRole('button', {
      name: /Start Round 1 Draft/i,
    });
    await expect(startButton).toBeVisible();
    await expect(startButton).toBeEnabled();
  });

  test('non-commissioner sees waiting state without start button', async ({
    authenticatedPage,
  }) => {
    // Commissioner is someone else
    const league = buildLeague({ commissioner_id: OTHER_USER_ID });
    await setupSupabaseMocks(authenticatedPage, {
      leagues: leagueHandler(league),
    });

    await authenticatedPage.goto(`/draft/${LEAGUE_ID}/lobby`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /Draft Lobby/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Start Draft button should NOT be visible
    await expect(
      authenticatedPage.getByRole('button', { name: /Start.*Draft/i })
    ).not.toBeVisible();

    // Waiting for Commissioner alert should be visible
    await expect(
      authenticatedPage.getByText(/commissioner will start the draft/i)
    ).toBeVisible();
  });
});
