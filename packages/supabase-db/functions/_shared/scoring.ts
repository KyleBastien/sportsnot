// Deno-compatible fantasy scoring utilities used by edge functions.
//
// Mirrors the pure functions in packages/utils/src/lib/utils.ts. Kept as a
// small vendored copy (rather than importing @sportsnot/utils) because the
// Supabase edge runtime resolves imports from URLs/relative paths, not Nx
// workspace aliases.
//
// Parity with the TS source is enforced by
// packages/supabase-db/functions/_shared/scoring.test.ts.

export const SCORING = {
  goal: 1,
  assist: 1,
  win: 2,
  shutout: 4,
} as const;

export interface SkaterStatLine {
  goals: number;
  assists: number;
}

export interface GoalieGameLine {
  teamScore: number;
  opponentScore: number;
}

/** Fantasy points for a skater from goal/assist totals. */
export function calculatePlayerPoints(stats: SkaterStatLine): number {
  return stats.goals * SCORING.goal + stats.assists * SCORING.assist;
}

/** Fantasy points for a single goalie game (shutout replaces win, not additive). */
export function calculateGoalieGamePoints(
  teamScore: number,
  opponentScore: number
): number {
  if (teamScore <= opponentScore) return 0;
  return opponentScore === 0 ? SCORING.shutout : SCORING.win;
}

/** Fantasy points for a goalie across a set of completed games. */
export function calculateGoaliePointsFromGames(
  games: GoalieGameLine[]
): number {
  let total = 0;
  for (const g of games) {
    total += calculateGoalieGamePoints(g.teamScore, g.opponentScore);
  }
  return total;
}
