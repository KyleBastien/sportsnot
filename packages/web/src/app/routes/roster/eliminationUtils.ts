/**
 * Compute roster slot elimination from team_stats_cache rows.
 *
 * Background
 * ----------
 * The `team_stats_cache.is_eliminated` column is currently populated as
 * `false` by `syncRoundTeamStats` for every team that participated in a
 * round. So we cannot rely on the flag alone in production. Instead we
 * derive the alive set from cache row presence:
 *
 *   - A team is "alive" entering round R+1 iff it has a `team_stats_cache`
 *     row for round R+1.
 *   - When viewing round R (R < 4) and the round-(R+1) cache is populated,
 *     a slot is eliminated if its NHL team is not in that alive set.
 *   - When viewing round R = 4 (Stanley Cup Final) there is no round 5
 *     cache, so we fall back to round-4 cache row presence (only the two
 *     finalists have rows). A team additionally counts as eliminated if its
 *     row exists with `is_eliminated = true`.
 *   - When the next round's cache is empty (e.g., R+1 not yet synced), we
 *     fall back to the current round's cache and only mark teams whose
 *     row has `is_eliminated = true`. This is a graceful degrade — players
 *     stay un-crossed until the next sync runs.
 *
 * Round 3 + 4 combined draft
 * --------------------------
 * The Round 3 draft fills both R3 and R4 rosters (via auto-copy). When a
 * user views their R4 roster, players whose teams lost in R3 must show as
 * crossed out. That happens automatically: those teams have no row in the
 * round-4 cache, so they are not in the R4 alive set.
 *
 * Resolving slot → team
 * ---------------------
 * Skater slots only carry `player_id`; we map player_id → team_id via the
 * `player_stats_cache` rows for whichever round resolves names (typically
 * the current round, or round 3 when current round is 4 — see
 * `useRosterStatsData`). Team picks (goalies) carry `team_id` directly.
 */

export interface TeamStatRowLike {
  team_id: number;
  team_abbreviation?: string | null;
  is_eliminated?: boolean | null;
}

export interface PlayerStatRowLike {
  player_id: number;
  team_abbreviation?: string | null;
}

export interface SlotForElimination {
  player_id: number | null;
  team_id: number | null;
}

export interface EliminationMaps {
  /** team_ids still alive in the displayed round (inclusive). */
  aliveTeamIds: Set<number>;
  /** player_id → NHL team_id, for slot resolution. */
  playerTeamIdByPlayerId: Map<number, number>;
  /** false until cache data has loaded; while false, no slot is marked. */
  hasEliminationData: boolean;
}

export function buildPlayerTeamIdMap(
  playerStats: ReadonlyArray<PlayerStatRowLike>,
  ...teamStatsSources: ReadonlyArray<ReadonlyArray<TeamStatRowLike>>
): Map<number, number> {
  const teamIdByAbbr = new Map<string, number>();
  for (const teamStats of teamStatsSources) {
    for (const row of teamStats) {
      if (row.team_abbreviation) {
        teamIdByAbbr.set(row.team_abbreviation, row.team_id);
      }
    }
  }

  const map = new Map<number, number>();
  for (const player of playerStats) {
    const abbr = player.team_abbreviation;
    if (!abbr) continue;
    const teamId = teamIdByAbbr.get(abbr);
    if (teamId != null) {
      map.set(player.player_id, teamId);
    }
  }
  return map;
}

export interface ComputeAliveTeamIdsParams {
  round: number;
  currentRoundTeamStats: ReadonlyArray<TeamStatRowLike>;
  nextRoundTeamStats: ReadonlyArray<TeamStatRowLike>;
}

export interface ComputeAliveTeamIdsResult {
  aliveTeamIds: Set<number>;
  hasEliminationData: boolean;
}

export function computeAliveTeamIds(
  params: ComputeAliveTeamIdsParams
): ComputeAliveTeamIdsResult {
  const { round, currentRoundTeamStats, nextRoundTeamStats } = params;

  if (round < 4 && nextRoundTeamStats.length > 0) {
    const alive = new Set<number>();
    for (const row of nextRoundTeamStats) {
      if (!row.is_eliminated) alive.add(row.team_id);
    }
    return { aliveTeamIds: alive, hasEliminationData: true };
  }

  if (currentRoundTeamStats.length > 0) {
    const alive = new Set<number>();
    for (const row of currentRoundTeamStats) {
      if (!row.is_eliminated) alive.add(row.team_id);
    }
    return { aliveTeamIds: alive, hasEliminationData: true };
  }

  return { aliveTeamIds: new Set(), hasEliminationData: false };
}

function resolveSlotTeamId(
  slot: SlotForElimination,
  playerTeamIdByPlayerId: Map<number, number>
): number | null {
  if (slot.player_id != null) {
    return playerTeamIdByPlayerId.get(slot.player_id) ?? null;
  }
  return slot.team_id;
}

export function isSlotEliminated(
  slot: SlotForElimination,
  maps: EliminationMaps
): boolean {
  if (!maps.hasEliminationData) return false;

  const teamId = resolveSlotTeamId(slot, maps.playerTeamIdByPlayerId);
  if (teamId == null) return false;

  return !maps.aliveTeamIds.has(teamId);
}

export function decorateSlotsWithElimination<
  T extends SlotForElimination & { is_eliminated?: boolean },
>(slots: ReadonlyArray<T>, maps: EliminationMaps): T[] {
  return slots.map((slot) => ({
    ...slot,
    is_eliminated: isSlotEliminated(slot, maps),
  }));
}
