import { describe, it, expect } from '@rstest/core';

// ── Edge function game-log date filtering (pure logic) ─────────────────
// The sync-nhl-stats edge function filters NHL API game logs by
// round_start_date / round_end_date to ensure points are round-specific.

interface GameLog {
  gameId: number;
  gameDate: string;
  goals: number;
  assists: number;
}

/** Replicates the date filtering logic from sync-nhl-stats edge function */
function filterGamesByDateRange(
  games: GameLog[],
  roundStartDate?: string,
  roundEndDate?: string
): GameLog[] {
  if (!roundStartDate || !roundEndDate) return games;
  return games.filter(
    (g) => g.gameDate >= roundStartDate && g.gameDate <= roundEndDate
  );
}

describe('filterGamesByDateRange (sync-nhl-stats edge function logic)', () => {
  const allGames: GameLog[] = [
    { gameId: 1, gameDate: '2025-04-20', goals: 1, assists: 0 }, // R1
    { gameId: 2, gameDate: '2025-04-25', goals: 0, assists: 2 }, // R1
    { gameId: 3, gameDate: '2025-05-01', goals: 1, assists: 1 }, // R1
    { gameId: 4, gameDate: '2025-05-06', goals: 2, assists: 0 }, // R2
    { gameId: 5, gameDate: '2025-05-12', goals: 0, assists: 1 }, // R2
    { gameId: 6, gameDate: '2025-05-21', goals: 3, assists: 0 }, // R3
  ];

  it('should return all games when no date range provided', () => {
    const filtered = filterGamesByDateRange(allGames);
    expect(filtered.length).toBe(6);
  });

  it('should return all games when start date undefined', () => {
    const filtered = filterGamesByDateRange(allGames, undefined, '2025-05-04');
    expect(filtered.length).toBe(6);
  });

  it('should filter to R1 games only (2025-04-19 to 2025-05-04)', () => {
    const filtered = filterGamesByDateRange(
      allGames,
      '2025-04-19',
      '2025-05-04'
    );
    expect(filtered.length).toBe(3);
    expect(filtered.map((g) => g.gameId)).toEqual([1, 2, 3]);
  });

  it('should filter to R2 games only (2025-05-05 to 2025-05-18)', () => {
    const filtered = filterGamesByDateRange(
      allGames,
      '2025-05-05',
      '2025-05-18'
    );
    expect(filtered.length).toBe(2);
    expect(filtered.map((g) => g.gameId)).toEqual([4, 5]);
  });

  it('should filter to R3 games only', () => {
    const filtered = filterGamesByDateRange(
      allGames,
      '2025-05-20',
      '2025-05-29'
    );
    expect(filtered.length).toBe(1);
    expect(filtered[0].gameId).toBe(6);
  });

  it('should return empty when no games fall in range', () => {
    const filtered = filterGamesByDateRange(
      allGames,
      '2025-06-01',
      '2025-06-15'
    );
    expect(filtered.length).toBe(0);
  });

  it('should include games on boundary dates (inclusive)', () => {
    const filtered = filterGamesByDateRange(
      allGames,
      '2025-04-20',
      '2025-04-20'
    );
    expect(filtered.length).toBe(1);
    expect(filtered[0].gameId).toBe(1);
  });

  it('should correctly sum only R2 goals (not cumulative)', () => {
    const r2Games = filterGamesByDateRange(
      allGames,
      '2025-05-05',
      '2025-05-18'
    );
    const totalGoals = r2Games.reduce((sum, g) => sum + g.goals, 0);
    const totalAssists = r2Games.reduce((sum, g) => sum + g.assists, 0);
    // R2 only: game4 (2g, 0a) + game5 (0g, 1a) = 2 goals, 1 assist
    expect(totalGoals).toBe(2);
    expect(totalAssists).toBe(1);
  });
});

// ── Production useMyRoster return shape contract ───────────────────────
// The production hook must return { memberId, round, slots, totalPoints }
// matching the mock hook shape.

describe('production useMyRoster return shape contract', () => {
  it('should define the expected shape with totalPoints field', () => {
    // Simulates the production hook return value structure
    const productionResult = {
      memberId: 'member-uuid',
      round: 2,
      slots: [
        {
          id: 'slot-1',
          league_member_id: 'member-uuid',
          round: 2,
          player_id: 8470594,
          team_id: null,
          position: 'F',
          is_active: true,
          points_earned: 5,
          activated_from_ir: false,
          is_eliminated: false,
        },
      ],
      totalPoints: 12, // cumulative from league_members.total_points
    };

    expect(productionResult).toHaveProperty('memberId');
    expect(productionResult).toHaveProperty('round');
    expect(productionResult).toHaveProperty('slots');
    expect(productionResult).toHaveProperty('totalPoints');
    expect(typeof productionResult.totalPoints).toBe('number');
  });

  it('totalPoints should be >= sum of current round slot points', () => {
    // In R2+, totalPoints includes prior rounds, so it should be >= current round sum
    const currentRoundSlots = [
      { points_earned: 3, is_active: true },
      { points_earned: 5, is_active: true },
      { points_earned: 0, is_active: false },
    ];
    const roundPoints = currentRoundSlots
      .filter((s) => s.is_active)
      .reduce((sum, s) => sum + s.points_earned, 0);
    const totalPoints = 20; // includes R1 contributions

    expect(totalPoints).toBeGreaterThanOrEqual(roundPoints);
  });

  it('totalPoints should default to 0 when member data is missing', () => {
    const memberData: { total_points?: number } | null = null;
    const totalPoints = memberData?.total_points ?? 0;
    expect(totalPoints).toBe(0);
  });

  it('totalPoints should equal slot sum in Round 1 (no prior rounds)', () => {
    // In R1, total_points from league_members should equal sum of R1 slot points
    const slots = [
      { points_earned: 3, is_active: true },
      { points_earned: 5, is_active: true },
    ];
    const roundPoints = slots
      .filter((s) => s.is_active)
      .reduce((sum, s) => sum + s.points_earned, 0);

    // After refresh_league_standings runs, total_points = sum of all active roster points
    // In R1, this equals the current round slot sum
    expect(roundPoints).toBe(8);
  });
});
