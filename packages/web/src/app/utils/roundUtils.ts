import type { NHLPlayoffSeries } from '@sportsnot/types';

interface RoundTeamStats {
  wins: number;
}

/**
 * Check whether every series in a given playoff round is complete.
 * A series is complete when one team has 4 wins.
 * Returns false when there are no series for the round (data not yet loaded).
 */
export function isAllSeriesComplete(
  allSeries: NHLPlayoffSeries[],
  round: number
): boolean {
  const roundSeries = allSeries.filter((s) => s.round === round);
  if (roundSeries.length === 0) return false;
  return roundSeries.every((s) => s.isComplete);
}

/**
 * Check whether a playoff round is complete from cached team win totals.
 *
 * Each round starts with a power-of-two team count. The round is complete when
 * exactly half of those teams have reached 4 wins.
 */
export function isRoundCompleteFromTeamStats(teams: RoundTeamStats[]): boolean {
  if (teams.length === 0 || teams.length % 2 !== 0) {
    return false;
  }

  const completedSeriesCount = teams.filter((team) => team.wins >= 4).length;
  return completedSeriesCount > 0 && completedSeriesCount * 2 === teams.length;
}

/**
 * Derive the current round number reliably.
 *
 * `league.current_round` can be stale, 0, or null between rounds. Completed
 * drafts are a stronger source of truth once a new round draft has already
 * finished, so we use the higher of the two values.
 */
export function deriveCurrentRound(
  leagueCurrentRound: number | null | undefined,
  completedDraftsCount: number
): number {
  const currentRoundValue =
    leagueCurrentRound && leagueCurrentRound > 0 ? leagueCurrentRound : 0;

  return Math.max(currentRoundValue, completedDraftsCount);
}

/**
 * Derive the next round number from the current round.
 */
export function deriveNextRound(
  leagueCurrentRound: number | null | undefined,
  completedDraftsCount: number
): number {
  return deriveCurrentRound(leagueCurrentRound, completedDraftsCount) + 1;
}
