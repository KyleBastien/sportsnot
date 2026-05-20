/**
 * Derive roster elimination from `team_stats_cache` row presence.
 *
 * Production sync currently writes `is_eliminated=false` for every cached row,
 * so the reliable signal is which teams appear in the next round's cache.
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
  aliveTeamIds: Set<number>;
  playerTeamIdByPlayerId: Map<number, number>;
  hasEliminationData: boolean;
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

type TeamStatsCollection = ReadonlyArray<TeamStatRowLike>;

export function buildPlayerTeamIdMap(
  playerStats: ReadonlyArray<PlayerStatRowLike>,
  ...teamStatsSources: ReadonlyArray<TeamStatsCollection>
): Map<number, number> {
  const teamIdByAbbreviation = buildTeamIdByAbbreviationMap(teamStatsSources);
  const playerTeamIds = new Map<number, number>();

  for (const player of playerStats) {
    const teamId = resolvePlayerTeamId(player, teamIdByAbbreviation);
    if (teamId != null) {
      playerTeamIds.set(player.player_id, teamId);
    }
  }

  return playerTeamIds;
}

export function computeAliveTeamIds(
  params: ComputeAliveTeamIdsParams
): ComputeAliveTeamIdsResult {
  const aliveTeamStats = selectAliveTeamStats(params);
  if (aliveTeamStats.length === 0) {
    return emptyAliveTeamIdsResult();
  }

  return {
    aliveTeamIds: collectAliveTeamIds(aliveTeamStats),
    hasEliminationData: true,
  };
}

export function isSlotEliminated(
  slot: SlotForElimination,
  maps: EliminationMaps
): boolean {
  if (!maps.hasEliminationData) {
    return false;
  }

  const teamId = resolveSlotTeamId(slot, maps.playerTeamIdByPlayerId);
  return teamId != null && !maps.aliveTeamIds.has(teamId);
}

export function decorateSlotsWithElimination<
  T extends SlotForElimination & { is_eliminated?: boolean },
>(slots: ReadonlyArray<T>, maps: EliminationMaps): T[] {
  return slots.map((slot) => ({
    ...slot,
    is_eliminated: isSlotEliminated(slot, maps),
  }));
}

function buildTeamIdByAbbreviationMap(
  teamStatsSources: ReadonlyArray<TeamStatsCollection>
): Map<string, number> {
  const teamIdByAbbreviation = new Map<string, number>();

  for (const teamStats of teamStatsSources) {
    addTeamIdsByAbbreviation(teamIdByAbbreviation, teamStats);
  }

  return teamIdByAbbreviation;
}

function addTeamIdsByAbbreviation(
  teamIdByAbbreviation: Map<string, number>,
  teamStats: TeamStatsCollection
) {
  for (const team of teamStats) {
    if (team.team_abbreviation) {
      teamIdByAbbreviation.set(team.team_abbreviation, team.team_id);
    }
  }
}

function resolvePlayerTeamId(
  player: PlayerStatRowLike,
  teamIdByAbbreviation: Map<string, number>
): number | null {
  if (!player.team_abbreviation) {
    return null;
  }

  return teamIdByAbbreviation.get(player.team_abbreviation) ?? null;
}

function selectAliveTeamStats(
  params: ComputeAliveTeamIdsParams
): TeamStatsCollection {
  if (shouldUseNextRoundTeamStats(params)) {
    return params.nextRoundTeamStats;
  }

  return params.currentRoundTeamStats;
}

function shouldUseNextRoundTeamStats(
  params: ComputeAliveTeamIdsParams
): boolean {
  return params.round < 4 && params.nextRoundTeamStats.length > 0;
}

function emptyAliveTeamIdsResult(): ComputeAliveTeamIdsResult {
  return {
    aliveTeamIds: new Set<number>(),
    hasEliminationData: false,
  };
}

function collectAliveTeamIds(teamStats: TeamStatsCollection): Set<number> {
  const aliveTeamIds = new Set<number>();

  for (const team of teamStats) {
    if (!team.is_eliminated) {
      aliveTeamIds.add(team.team_id);
    }
  }

  return aliveTeamIds;
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
