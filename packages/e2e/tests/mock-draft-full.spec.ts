import { test, expect } from '../fixtures/supabase-mock.fixture';
import {
  setupSupabaseMocks,
  mockTableList,
} from '../fixtures/supabase-mock.fixture';
import { mockUser, SUPABASE_URL } from '../fixtures/auth.fixture';

/**
 * Full draft end-to-end test using HTTP-level Supabase mocks.
 *
 * Stateful route handlers simulate a 4-member snake draft (44 picks).
 * Bot picks are auto-generated inside the mock when the human's pick
 * mutations complete, so the next poll returns "Your Turn!" immediately.
 *
 * Flow: Navigate to /draft/:leagueId → Make 11 human picks (with
 *       simulated bot picks between turns) → Draft Complete → Verify
 *       all 44 picks have no "Unknown" team names.
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const LEAGUE_ID = 'full-draft-league-aaaa-bbbb-cccccccccccc';
const DRAFT_ID = 'full-draft-0001-aaaa-bbbb-cccccccccccc';
const HUMAN_MEMBER_ID = 'member-human-0001';

const BOTS = [
  {
    userId: 'bot-1111-1111-1111-111111111111',
    memberId: 'member-bot-0001',
    teamName: 'Bot Alpha',
  },
  {
    userId: 'bot-2222-2222-2222-222222222222',
    memberId: 'member-bot-0002',
    teamName: 'Bot Beta',
  },
  {
    userId: 'bot-3333-3333-3333-333333333333',
    memberId: 'member-bot-0003',
    teamName: 'Bot Gamma',
  },
];

const ALL_USER_IDS = [mockUser.id, ...BOTS.map((b) => b.userId)];

const MEMBERS = [
  {
    id: HUMAN_MEMBER_ID,
    user_id: mockUser.id,
    team_name: 'E2E Team',
    total_points: 0,
    users: { display_name: 'Test User' },
  },
  ...BOTS.map((b) => ({
    id: b.memberId,
    user_id: b.userId,
    team_name: b.teamName,
    total_points: 0,
    users: { display_name: b.teamName },
  })),
];

// ---------------------------------------------------------------------------
// Snake draft order: 4 members × 11 rounds = 44 picks
// ---------------------------------------------------------------------------
function buildSnakeOrder(userIds: string[], rounds: number): string[] {
  const order: string[] = [];
  for (let r = 0; r < rounds; r++) {
    order.push(...(r % 2 === 0 ? userIds : [...userIds].reverse()));
  }
  return order;
}

const DRAFT_ORDER = buildSnakeOrder(ALL_USER_IDS, 11);

// ---------------------------------------------------------------------------
// Mock player / team data  (enough for 44 picks)
// ---------------------------------------------------------------------------
const SEASON = '20242025';

const mockForwards = Array.from({ length: 30 }, (_, i) => ({
  player_id: 9000 + i,
  nhl_season: SEASON,
  playoff_round: 1,
  player_name: `Forward ${String(i + 1).padStart(2, '0')}`,
  team_abbreviation: ['EDM', 'TOR', 'COL', 'WPG', 'TBL', 'CAR', 'NYR', 'BOS'][
    i % 8
  ],
  position: 'F',
  goals: 30 - i,
  assists: 20 - Math.floor(i / 2),
  games_played: 7,
  is_injured: false,
  last_updated: '2026-02-14T00:00:00Z',
}));

const mockDefensemen = Array.from({ length: 20 }, (_, i) => ({
  player_id: 9100 + i,
  nhl_season: SEASON,
  playoff_round: 1,
  player_name: `Defenseman ${String(i + 1).padStart(2, '0')}`,
  team_abbreviation: ['COL', 'TBL', 'VAN', 'NYR', 'DAL', 'EDM', 'TOR', 'WPG'][
    i % 8
  ],
  position: 'D',
  goals: 10 - Math.floor(i / 2),
  assists: 15 - i,
  games_played: 7,
  is_injured: false,
  last_updated: '2026-02-14T00:00:00Z',
}));

const mockTeams = Array.from({ length: 8 }, (_, i) => ({
  team_id: 100 + i,
  nhl_season: SEASON,
  playoff_round: 1,
  team_name: `Team ${String.fromCharCode(65 + i)}`,
  team_abbreviation: ['EDM', 'TOR', 'COL', 'WPG', 'TBL', 'CAR', 'NYR', 'BOS'][
    i
  ],
  wins: 8 - i,
  shutouts: i % 2,
  is_eliminated: false,
  last_updated: '2026-02-14T00:00:00Z',
}));

const regSeasonStats = [
  ...mockForwards.map((p, i) => ({
    player_id: p.player_id,
    nhl_season: SEASON,
    points: 100 - i,
  })),
  ...mockDefensemen.map((p, i) => ({
    player_id: p.player_id,
    nhl_season: SEASON,
    points: 80 - i,
  })),
];

// ---------------------------------------------------------------------------
// Pick shape returned in draft_picks
// ---------------------------------------------------------------------------
interface PickState {
  id: string;
  pick_number: number;
  player_id: number | null;
  team_id: number | null;
  position: string;
  league_members: { team_name: string; user_id: string };
}

// ---------------------------------------------------------------------------
// Draft simulator — encapsulates mutable state and bot-pick logic
// outside the test body to satisfy playwright/no-conditional-in-test.
// ---------------------------------------------------------------------------
const SLOT_LIMITS: Record<string, number> = {
  F: 5,
  D: 3,
  G: 1,
  IR_F: 1,
  IR_D: 1,
};

const POSITION_PRIORITY: Array<{
  pos: string;
  pool: 'availF' | 'availD' | 'availG';
  idField: 'player_id' | 'team_id';
}> = [
  { pos: 'F', pool: 'availF', idField: 'player_id' },
  { pos: 'D', pool: 'availD', idField: 'player_id' },
  { pos: 'G', pool: 'availG', idField: 'team_id' },
  { pos: 'IR_F', pool: 'availF', idField: 'player_id' },
  { pos: 'IR_D', pool: 'availD', idField: 'player_id' },
];

class DraftSimulator {
  currentPick = 1;
  picks: PickState[] = [];
  status = 'active';
  availF: number[];
  availD: number[];
  availG: number[];
  slots: Record<string, Record<string, number>>;

  constructor() {
    this.availF = mockForwards.map((p) => p.player_id);
    this.availD = mockDefensemen.map((p) => p.player_id);
    this.availG = mockTeams.map((t) => t.team_id);
    this.slots = {};
    for (const m of MEMBERS) {
      this.slots[m.user_id] = { F: 0, D: 0, G: 0, IR_F: 0, IR_D: 0 };
    }
  }

  private poolFor(key: 'availF' | 'availD' | 'availG'): number[] {
    return this[key];
  }

  makeBotPick(pickNum: number, userId: string): PickState {
    const member = MEMBERS.find((m) => m.user_id === userId)!;
    const s = this.slots[userId];
    const match =
      POSITION_PRIORITY.find(
        ({ pos, pool }) =>
          s[pos] < SLOT_LIMITS[pos] && this.poolFor(pool).length
      ) ?? POSITION_PRIORITY[0];

    const pool = this.poolFor(match.pool);
    const id = pool.shift() ?? 99999;
    s[match.pos]++;

    return {
      id: `pick-${pickNum}`,
      pick_number: pickNum,
      player_id: match.idField === 'player_id' ? id : null,
      team_id: match.idField === 'team_id' ? id : null,
      position: match.pos,
      league_members: { team_name: member.team_name, user_id: userId },
    };
  }

  advanceBots() {
    while (
      this.currentPick <= 44 &&
      DRAFT_ORDER[this.currentPick - 1] !== mockUser.id
    ) {
      this.picks.push(
        this.makeBotPick(this.currentPick, DRAFT_ORDER[this.currentPick - 1])
      );
      this.currentPick++;
    }
    if (this.currentPick > 44) {
      this.status = 'completed';
    }
  }

  recordHumanPick(body: {
    pick_number: number;
    player_id: number | null;
    team_id: number | null;
    position: string;
  }): PickState {
    const member = MEMBERS.find((m) => m.user_id === mockUser.id)!;
    const humanPick: PickState = {
      id: `pick-${this.currentPick}`,
      pick_number: body.pick_number,
      player_id: body.player_id,
      team_id: body.team_id,
      position: body.position,
      league_members: {
        team_name: member.team_name,
        user_id: mockUser.id,
      },
    };
    this.picks.push(humanPick);
    this.slots[mockUser.id][body.position]++;

    for (const pool of [this.availF, this.availD]) {
      const idx = pool.indexOf(body.player_id ?? -1);
      if (idx >= 0) pool.splice(idx, 1);
    }
    const tIdx = this.availG.indexOf(body.team_id ?? -1);
    if (tIdx >= 0) this.availG.splice(tIdx, 1);

    this.currentPick++;
    return humanPick;
  }

  snapshot() {
    return {
      id: DRAFT_ID,
      league_id: LEAGUE_ID,
      round: 1,
      status: this.status,
      current_pick: this.currentPick,
      draft_order: DRAFT_ORDER,
      started_at: '2026-02-14T12:00:00.000Z',
      completed_at:
        this.status === 'completed' ? '2026-02-14T13:00:00.000Z' : null,
      draft_picks: this.picks.map((p) => ({ ...p })),
    };
  }
}

// ---------------------------------------------------------------------------
// Route handler factories (keep conditionals out of test body)
// ---------------------------------------------------------------------------
function draftsHandler(sim: DraftSimulator) {
  return async (route: import('@playwright/test').Route) => {
    const method = route.request().method();
    const accept = route.request().headers()['accept'] ?? '';

    if (method === 'GET') {
      const snap = sim.snapshot();
      if (accept.includes('vnd.pgrst.object+json')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(snap),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([snap]),
      });
    }

    if (method === 'PATCH') {
      sim.advanceBots();
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '{}',
      });
    }

    return route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: '{}',
    });
  };
}

function draftPicksHandler(sim: DraftSimulator) {
  return async (route: import('@playwright/test').Route) => {
    if (route.request().method() === 'POST') {
      const body = JSON.parse(route.request().postData()!);
      const humanPick = sim.recordHumanPick(body);
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(humanPick),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '[]',
    });
  };
}

function leaguesHandler() {
  return async (route: import('@playwright/test').Route) => {
    const body = route.request().method() === 'PATCH' ? '{}' : '[]';
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body,
    });
  };
}

// ---------------------------------------------------------------------------
// Test
// ---------------------------------------------------------------------------
test.describe('Full Mock Draft', () => {
  test('completes a full 44-pick, 4-member, 11-round draft without Unknown', async ({
    authenticatedPage: page,
  }) => {
    test.setTimeout(180_000); // 3 minutes for full draft

    const sim = new DraftSimulator();
    sim.advanceBots(); // no-op — human picks first

    // ── Route setup ──────────────────────────────────────────────────
    await setupSupabaseMocks(page, {
      drafts: draftsHandler(sim),
      draft_picks: draftPicksHandler(sim),
      league_members: mockTableList(MEMBERS),
      player_stats_cache: mockTableList([...mockForwards, ...mockDefensemen]),
      team_stats_cache: mockTableList(mockTeams),
      rosters: async (route) => {
        return route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: '{}',
        });
      },
      leagues: leaguesHandler(),
    });

    // regular_season_stats_cache is not in the default mocked tables
    await page.route(
      `${SUPABASE_URL}/rest/v1/regular_season_stats_cache*`,
      async (route) => {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(regSeasonStats),
        });
      }
    );

    // ── Step 1: Navigate to draft page ───────────────────────────────
    await page.goto(`/draft/${LEAGUE_ID}`);

    await expect(
      page.getByRole('heading', { name: /Draft Room/i })
    ).toBeVisible({ timeout: 15_000 });

    // ── Step 2: Complete all 11 human picks ──────────────────────────
    // Roster composition: 5F + 3D + 1G + 1 IR-F + 1 IR-D = 11 slots
    const positionFilters = [
      'Forwards', // F slot 1
      'Forwards', // F slot 2
      'Forwards', // F slot 3
      'Forwards', // F slot 4
      'Forwards', // F slot 5
      'Goalies', // G slot
      'Defense', // D slot 1
      'Defense', // D slot 2
      'Defense', // D slot 3
      'Forwards', // IR-F slot (auto-selected by smart pre-selection)
      'Defense', // IR-D slot (auto-selected by smart pre-selection)
    ];

    for (let pick = 0; pick < 11; pick++) {
      // Wait for "Your Turn!" badge (bots resolve on next poll ~3 s)
      await expect(page.getByText('Your Turn!')).toBeVisible({
        timeout: 45_000,
      });

      // Verify no "Unknown" is shown for the current turn
      await expect(
        page.locator('text=Pick #').locator('..').locator('..')
      ).not.toContainText('Unknown');

      // Filter by the needed position
      await page.locator(`label:has-text("${positionFilters[pick]}")`).click();

      // Click first available "Draft" button
      const draftBtn = page.getByRole('button', { name: /^Draft$/i }).first();
      await expect(draftBtn).toBeVisible({ timeout: 5_000 });
      await draftBtn.click();

      // Confirm pick in the modal
      const confirmBtn = page.getByRole('button', {
        name: /Confirm Pick/i,
      });
      await expect(confirmBtn).toBeVisible({ timeout: 5_000 });
      await confirmBtn.click();

      // Wait for modal to close before next iteration
      await expect(page.getByRole('dialog')).toBeHidden({
        timeout: 5_000,
      });
    }

    // ── Step 3: Wait for draft completion ────────────────────────────
    // After the human's 11th pick, bots finish remaining 3 picks and
    // the next poll returns status='completed'.
    await expect(
      page.getByRole('heading', { name: /Draft Complete/i })
    ).toBeVisible({ timeout: 60_000 });

    // All 44 picks accounted for
    await expect(page.getByText(/All 44 picks have been made/i)).toBeVisible();

    // ── Step 4: Verify no "Unknown" in the final history table ───────
    const historyTable = page.getByRole('table');
    await expect(historyTable).toBeVisible();

    const rows = historyTable.getByRole('row');
    const rowCount = await rows.count();

    // At least 44 data rows + 1 header row
    expect(rowCount).toBeGreaterThanOrEqual(45);

    // Every data row (skip header at index 0) must not contain "Unknown"
    for (let i = 1; i < rowCount; i++) {
      await expect(rows.nth(i)).not.toContainText('Unknown');
    }
  });
});
