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
