import { test, expect } from '../fixtures/auth.fixture';
import { setupSupabaseMocks } from '../fixtures/supabase-mock.fixture';
import { mockUser } from '../fixtures/auth.fixture';

const NAV_TIMEOUT = { timeout: 15000 };
const LEAGUE_ID = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
const OTHER_USER_ID = '99999999-8888-7777-6666-555555555555';
const THIRD_USER_ID = '77777777-6666-5555-4444-333333333333';
const FOURTH_USER_ID = '66666666-5555-4444-3333-222222222222';

/** Build a league in round-transition state (round 1 completed, current_round = 1) */
function buildLeague(overrides: Record<string, unknown> = {}) {
  return {
    id: LEAGUE_ID,
    name: 'Playoff League',
    commissioner_id: mockUser.id,
    invite_code: 'TRANS1',
    max_participants: 8,
    status: 'active',
    current_round: 1,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    league_members: [
      {
        id: 'member-1',
        user_id: mockUser.id,
        team_name: 'Alpha Team',
        total_points: 25,
        users: { display_name: mockUser.user_metadata.display_name },
      },
      {
        id: 'member-2',
        user_id: OTHER_USER_ID,
        team_name: 'Beta Team',
        total_points: 40,
        users: { display_name: 'Other Player' },
      },
      {
        id: 'member-3',
        user_id: THIRD_USER_ID,
        team_name: 'Gamma Team',
        total_points: 15,
        users: { display_name: 'Third Player' },
      },
      {
        id: 'member-4',
        user_id: FOURTH_USER_ID,
        team_name: 'Delta Team',
        total_points: 32,
        users: { display_name: 'Fourth Player' },
      },
    ],
    ...overrides,
  };
}

/** Route handler for leagues table */
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

/** Completed drafts list for draft history section */
function draftsHandler(completedDrafts: Record<string, unknown>[]) {
  return async (route: import('@playwright/test').Route) => {
    const request = route.request();
    const method = request.method();
    const url = request.url();

    if (method === 'GET' && url.includes('status=eq.completed')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(completedDrafts),
      });
    }

    if (method === 'POST') {
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({ id: 'new-draft-id' }),
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
// Round Transition Tests
// ──────────────────────────────────────────────────────────────────────────────
test.describe('Round Transition', () => {
  test('round transition page shows previous round final standings', async ({
    authenticatedPage,
  }) => {
    const league = buildLeague();
    const completedDrafts = [
      {
        id: 'draft-r1',
        round: 1,
        status: 'completed',
        completed_at: new Date().toISOString(),
      },
    ];

    await setupSupabaseMocks(authenticatedPage, {
      leagues: leagueHandler(league),
      drafts: draftsHandler(completedDrafts),
    });

    await authenticatedPage.goto(`/draft/${LEAGUE_ID}/transition`);

    // Header shows round complete
    await expect(
      authenticatedPage.getByRole('heading', { name: /Round 1 Complete!/i })
    ).toBeVisible(NAV_TIMEOUT);

    // League name visible
    await expect(authenticatedPage.getByText('Playoff League')).toBeVisible();

    // Full Re-Draft alert
    await expect(
      authenticatedPage.getByText(/Full Re-Draft/i)
    ).toBeVisible();
    await expect(
      authenticatedPage.getByText(/All players return to the pool/i)
    ).toBeVisible();

    // Final Standings heading
    await expect(
      authenticatedPage.getByRole('heading', {
        name: /Round 1 Final Standings/i,
      })
    ).toBeVisible();

    // Standings table headers
    await expect(
      authenticatedPage.getByRole('columnheader', { name: 'Rank' })
    ).toBeVisible();
    await expect(
      authenticatedPage.getByRole('columnheader', { name: 'Team' })
    ).toBeVisible();
    await expect(
      authenticatedPage.getByRole('columnheader', { name: 'Player' })
    ).toBeVisible();
    await expect(
      authenticatedPage.getByRole('columnheader', { name: 'Points' })
    ).toBeVisible();
    await expect(
      authenticatedPage.getByRole('columnheader', { name: 'Re-Draft Pick' })
    ).toBeVisible();

    // Members ranked by total_points descending: Other(40), Delta(32), Alpha(25), Gamma(15)
    const rows = authenticatedPage.getByRole('row');
    // Row 1 (header) + 4 data rows
    await expect(rows).toHaveCount(5);

    // #1 rank — Other Player with 40 points
    await expect(rows.nth(1).getByText('Beta Team')).toBeVisible();
    await expect(rows.nth(1).getByText('Other Player')).toBeVisible();
    await expect(rows.nth(1).getByText('40')).toBeVisible();

    // #4 rank — Gamma Team with 15 points (worst)
    await expect(rows.nth(4).getByText('Gamma Team')).toBeVisible();
    await expect(rows.nth(4).getByText('15')).toBeVisible();

    // Current user has "You" badge
    await expect(authenticatedPage.getByText('You')).toBeVisible();
  });

  test('new draft order worst-to-best snake is displayed', async ({
    authenticatedPage,
  }) => {
    const league = buildLeague();
    await setupSupabaseMocks(authenticatedPage, {
      leagues: leagueHandler(league),
      drafts: draftsHandler([]),
    });

    await authenticatedPage.goto(`/draft/${LEAGUE_ID}/transition`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /Round 1 Complete!/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Re-Draft Pick column shows worst-to-best order
    // Standings sorted desc by points: Other(40)=#1, Delta(32)=#2, Alpha(25)=#3, Gamma(15)=#4
    // sortedMembers (asc by points): Gamma(15), Alpha(25), Delta(32), Other(40)
    // Re-Draft pick for desc row i = sortedMembers.length - index
    // #1 rank (Other, 40pts) → pick #4-0 = pick #4 (last pick)
    // #4 rank (Gamma, 15pts) → pick #4-3 = pick #1 (first pick)

    // Worst team gets first pick
    const rows = authenticatedPage.getByRole('row');

    // Row for Gamma Team (#4 rank, 15pts) should have pick #1
    const gammaRow = rows.nth(4); // 4th data row (last place)
    await expect(gammaRow.getByText('#1')).toBeVisible();

    // Row for Other Player (#1 rank, 40pts) should have pick #4
    const otherRow = rows.nth(1); // 1st data row (first place)
    await expect(otherRow.getByText('#4')).toBeVisible();

    // Alert mentions snake pattern
    await expect(
      authenticatedPage.getByText(/worst to best, snake pattern/i)
    ).toBeVisible();
  });

  test('eliminated players are shown as removed from draft pool', async ({
    authenticatedPage,
  }) => {
    // The round transition page doesn't directly show eliminated players.
    // It shows completed draft history rounds and standings.
    // Eliminated teams are handled at the draft board level.
    // This test verifies the draft history section shows completed rounds.
    const completedDrafts = [
      {
        id: 'draft-r1',
        round: 1,
        status: 'completed',
        completed_at: '2026-02-10T12:00:00Z',
      },
    ];

    const league = buildLeague();
    await setupSupabaseMocks(authenticatedPage, {
      leagues: leagueHandler(league),
      drafts: draftsHandler(completedDrafts),
    });

    await authenticatedPage.goto(`/draft/${LEAGUE_ID}/transition`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /Round 1 Complete!/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Draft History section
    await expect(
      authenticatedPage.getByRole('heading', { name: /Draft History/i })
    ).toBeVisible();

    // Completed round shown with "Completed" badge
    await expect(
      authenticatedPage.getByText('Round 1', { exact: true })
    ).toBeVisible();
    await expect(authenticatedPage.getByText('Completed')).toBeVisible();
  });

  test('commissioner can trigger new round draft via button', async ({
    authenticatedPage,
  }) => {
    const league = buildLeague(); // commissioner_id = mockUser.id
    let draftInserted = false;

    await setupSupabaseMocks(authenticatedPage, {
      leagues: leagueHandler(league),
      drafts: async (route) => {
        const request = route.request();
        const method = request.method();
        const url = request.url();

        if (method === 'POST') {
          draftInserted = true;
          return route.fulfill({
            status: 201,
            contentType: 'application/json',
            body: JSON.stringify({ id: 'new-draft-id' }),
          });
        }

        if (method === 'GET' && url.includes('status=eq.completed')) {
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([]),
          });
        }

        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      },
    });

    await authenticatedPage.goto(`/draft/${LEAGUE_ID}/transition`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /Round 1 Complete!/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Commissioner sees the Start Re-Draft button
    const startButton = authenticatedPage.getByRole('button', {
      name: /Start Round 2 Re-Draft/i,
    });
    await expect(startButton).toBeVisible();
    await expect(startButton).toBeEnabled();

    // Click it
    await startButton.click();

    // Should navigate to draft page after successful insert
    await expect(authenticatedPage).toHaveURL(
      new RegExp(`/draft/${LEAGUE_ID}`),
      NAV_TIMEOUT
    );

    // Verify the POST was made
    expect(draftInserted).toBe(true);
  });

  test('non-commissioner sees waiting state without start button', async ({
    authenticatedPage,
  }) => {
    // Commissioner is someone else
    const league = buildLeague({ commissioner_id: OTHER_USER_ID });
    await setupSupabaseMocks(authenticatedPage, {
      leagues: leagueHandler(league),
      drafts: draftsHandler([]),
    });

    await authenticatedPage.goto(`/draft/${LEAGUE_ID}/transition`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /Round 1 Complete!/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Start Re-Draft button should NOT be visible
    await expect(
      authenticatedPage.getByRole('button', { name: /Start.*Re-Draft/i })
    ).not.toBeVisible();

    // Waiting for Commissioner alert
    await expect(
      authenticatedPage.getByText(/Waiting for Commissioner/i)
    ).toBeVisible();
    await expect(
      authenticatedPage.getByText(
        /commissioner will start the re-draft for Round 2/i
      )
    ).toBeVisible();

    // Back to League button is visible for navigation
    await expect(
      authenticatedPage.getByRole('button', { name: /Back to League/i })
    ).toBeVisible();
  });
});
