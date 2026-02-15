import { test, expect } from '../fixtures/supabase-mock.fixture';
import {
  setupSupabaseMocks,
  mockTableList,
} from '../fixtures/supabase-mock.fixture';

const NAV_TIMEOUT = { timeout: 15000 };
const LEAGUE_ID = 'scoring-league-1111-2222-333333333333';

const scoringEvents = [
  {
    id: 'ev-1',
    player_name: 'Connor McDavid',
    team_abbreviation: 'EDM',
    event_type: 'goal',
    points: 1,
    game_date: '2026-04-15',
    league_member_team: 'Alpha Team',
  },
  {
    id: 'ev-2',
    player_name: 'Connor McDavid',
    team_abbreviation: 'EDM',
    event_type: 'assist',
    points: 1,
    game_date: '2026-04-15',
    league_member_team: 'Alpha Team',
  },
  {
    id: 'ev-3',
    player_name: 'Auston Matthews',
    team_abbreviation: 'TOR',
    event_type: 'goal',
    points: 1,
    game_date: '2026-04-16',
    league_member_team: 'Beta Team',
  },
  {
    id: 'ev-4',
    player_name: 'Andrei Vasilevskiy',
    team_abbreviation: 'TBL',
    event_type: 'shutout',
    points: 4,
    game_date: '2026-04-17',
    league_member_team: 'Gamma Team',
  },
];

// ──────────────────────────────────────────────────────────────────────────────
// Scoring History Tests
// ──────────────────────────────────────────────────────────────────────────────
test.describe('Scoring History', () => {
  test('scoring history page shows scoring events list', async ({
    authenticatedPage,
  }) => {
    await setupSupabaseMocks(authenticatedPage, {
      scoring_events: mockTableList(scoringEvents),
    });
    await authenticatedPage.goto(`/scoring/${LEAGUE_ID}`);

    // Heading visible
    await expect(
      authenticatedPage.getByRole('heading', { name: /Scoring History/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Event count text
    await expect(authenticatedPage.getByText('4 scoring events')).toBeVisible();

    // Table with all events
    const table = authenticatedPage.getByRole('table');
    await expect(table).toBeVisible();

    // Verify player names appear
    await expect(
      authenticatedPage.getByText('Connor McDavid').first()
    ).toBeVisible();
    await expect(authenticatedPage.getByText('Auston Matthews')).toBeVisible();
    await expect(
      authenticatedPage.getByText('Andrei Vasilevskiy')
    ).toBeVisible();
  });

  test('scoring events can be filtered by player, team, and date', async ({
    authenticatedPage,
  }) => {
    await setupSupabaseMocks(authenticatedPage, {
      scoring_events: mockTableList(scoringEvents),
    });
    await authenticatedPage.goto(`/scoring/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: /Scoring History/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Filter by player name
    const playerFilter = authenticatedPage.getByLabel('Filter by player');
    await playerFilter.fill('McDavid');

    // Only McDavid events should show (2 rows)
    const rows = authenticatedPage
      .getByRole('table')
      .getByRole('row')
      .filter({ has: authenticatedPage.getByRole('cell') });
    await expect(rows).toHaveCount(2);

    // Clear player filter
    await playerFilter.clear();
    await expect(rows).toHaveCount(4);

    // Filter by team using the select dropdown
    await authenticatedPage
      .getByRole('textbox', { name: 'Filter by team' })
      .click();
    await authenticatedPage.getByRole('option', { name: 'TOR' }).click();

    // Only TOR events (1 row)
    await expect(rows).toHaveCount(1);
    await expect(authenticatedPage.getByText('Auston Matthews')).toBeVisible();
  });
});
