import type { NHLPlayoffSeries } from '@sportsnot/types';

interface RoundTeamStats {
  wins: number;
}

type RoundPointsLike =
  | Record<string, number>
  | Record<number, number>
  | null
  | undefined;

export const MAX_PLAYOFF_ROUND = 4;

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
 * `league.current_round` can be 0 or null between rounds (e.g. after a round
 * completes but before the next draft starts). In that case we fall back to
 * `completedDraftsCount` which is always accurate.
 */
export function deriveCurrentRound(
  leagueCurrentRound: number | null | undefined,
  completedDraftsCount: number
): number {
  if (leagueCurrentRound && leagueCurrentRound > 0) {
    return leagueCurrentRound;
  }
  return completedDraftsCount;
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

export function clampRoundSelection(
  selectedRound: number | string | null | undefined,
  currentRound: number
): number {
  const cappedCurrentRound = Math.min(
    Math.max(currentRound, 1),
    MAX_PLAYOFF_ROUND
  );
  const parsedRound =
    typeof selectedRound === 'number'
      ? selectedRound
      : Number.parseInt(selectedRound ?? '', 10);

  if (!Number.isInteger(parsedRound)) {
    return cappedCurrentRound;
  }

  return Math.min(Math.max(parsedRound, 1), cappedCurrentRound);
}

export function getAvailableRounds(currentRound: number): number[] {
  const cappedCurrentRound = Math.min(
    Math.max(currentRound, 1),
    MAX_PLAYOFF_ROUND
  );

  return Array.from({ length: cappedCurrentRound }, (_, index) => index + 1);
}

export function getRoundPoints(
  roundPoints: RoundPointsLike,
  round: number
): number {
  return roundPoints?.[round] ?? roundPoints?.[String(round)] ?? 0;
}

export function sumRoundPointsThroughRound(
  roundPoints: RoundPointsLike,
  round: number
): number {
  let total = 0;

  for (let currentRound = 1; currentRound <= round; currentRound += 1) {
    total += getRoundPoints(roundPoints, currentRound);
  }

  return total;
}

export function buildRoundSearch(
  selectedRound: number,
  currentRound: number
): string {
  const normalizedCurrentRound = clampRoundSelection(
    currentRound,
    currentRound
  );
  const normalizedSelectedRound = clampRoundSelection(
    selectedRound,
    currentRound
  );

  if (normalizedSelectedRound === normalizedCurrentRound) {
    return '';
  }

  return `?round=${normalizedSelectedRound}`;
}
