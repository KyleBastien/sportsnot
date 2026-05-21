import type {
  DraftablePlayer,
  DraftRosterComposition,
  MySlotCounts,
  PlayerStatRow,
  RegSeasonStatRow,
  TeamStatRow,
} from './draftPageTypes';

export interface DraftSkaterRow extends DraftablePlayer {
  goals: number;
  assists: number;
  points: number;
  gamesPlayed: number;
  regSeasonPts: number;
}

export interface DraftTeamRow {
  id: number;
  fullName: string;
  team: string;
  teamId: number;
  wins: number;
  shutouts: number;
}

interface DraftSearchFilter {
  positionFilter: string;
  query: string;
}

const SKATER_POSITIONS = new Set(['F', 'D']);

export function shouldUseRegSeasonFallback(params: {
  isRound1: boolean;
  playerStats: PlayerStatRow[];
}): boolean {
  const { isRound1, playerStats } = params;
  return (
    isRound1 &&
    (playerStats.length === 0 ||
      playerStats.every((player) => (player.games_played ?? 0) === 0))
  );
}

export function buildSkaterRows(params: {
  playerStats: PlayerStatRow[];
  cumulativePlayerStats: PlayerStatRow[];
  regSeasonStats: RegSeasonStatRow[];
  draftedPlayerIds: Set<number>;
  isRound1: boolean;
}): DraftSkaterRow[] {
  const {
    playerStats,
    cumulativePlayerStats,
    regSeasonStats,
    draftedPlayerIds,
    isRound1,
  } = params;
  const regSeasonMap = new Map(
    regSeasonStats.map((row) => [row.player_id, row])
  );
  const cumulativeStatsMap = new Map(
    cumulativePlayerStats.map((row) => [row.player_id, row])
  );

  if (shouldUseRegSeasonFallback({ isRound1, playerStats })) {
    return regSeasonStats
      .filter((player) => isSkaterPosition(player.position))
      .filter((player) => !draftedPlayerIds.has(player.player_id))
      .map((player) => ({
        id: player.player_id,
        fullName: player.player_name ?? `Player #${player.player_id}`,
        firstName: '',
        lastName: '',
        position: player.position ?? 'F',
        team: player.team_abbreviation ?? 'NHL',
        teamId: 0,
        goals: player.goals ?? 0,
        assists: player.assists ?? 0,
        points: player.points ?? 0,
        gamesPlayed: player.games_played ?? 0,
        regSeasonPts: player.points ?? 0,
      }));
  }

  return playerStats
    .filter((player) => !draftedPlayerIds.has(player.player_id))
    .filter((player) => !player.is_injured)
    .map((player) => {
      const regSeason = regSeasonMap.get(player.player_id);
      const cumulativeStats = cumulativeStatsMap.get(player.player_id);
      const goals = cumulativeStats?.goals ?? player.goals ?? 0;
      const assists = cumulativeStats?.assists ?? player.assists ?? 0;
      return {
        id: player.player_id,
        fullName:
          player.player_name ??
          regSeason?.player_name ??
          `Player #${player.player_id}`,
        firstName: '',
        lastName: '',
        position: player.position ?? regSeason?.position ?? 'F',
        team: player.team_abbreviation ?? regSeason?.team_abbreviation ?? 'NHL',
        teamId: 0,
        goals,
        assists,
        points: goals + assists,
        gamesPlayed: cumulativeStats?.games_played ?? player.games_played ?? 0,
        regSeasonPts: regSeason?.points ?? 0,
      };
    });
}

export function buildTeamRows(params: {
  teamStats: TeamStatRow[];
  cumulativeTeamStats: TeamStatRow[];
  draftedTeamIds: Set<number>;
}): DraftTeamRow[] {
  const { teamStats, cumulativeTeamStats, draftedTeamIds } = params;
  const cumulativeStatsMap = new Map(
    cumulativeTeamStats.map((row) => [row.team_id, row])
  );
  return teamStats
    .filter((team) => !draftedTeamIds.has(team.team_id))
    .filter((team) => !team.is_eliminated)
    .map((team) => {
      const cumulativeStats = cumulativeStatsMap.get(team.team_id);
      return {
        id: team.team_id,
        fullName: team.team_name ?? `Team #${team.team_id}`,
        team: team.team_abbreviation ?? `Team #${team.team_id}`,
        teamId: team.team_id,
        wins: cumulativeStats?.wins ?? team.wins ?? 0,
        shutouts: cumulativeStats?.shutouts ?? team.shutouts ?? 0,
      };
    });
}

export function filterSkaterRows(params: {
  skaterRows: DraftSkaterRow[];
  positionFilter: string;
  searchQuery: string;
  isRound1: boolean;
}): DraftSkaterRow[] {
  const { skaterRows, positionFilter, searchQuery, isRound1 } = params;
  const filter = buildDraftSearchFilter(positionFilter, searchQuery);
  return skaterRows
    .filter((player) =>
      matchesDraftRow({
        fullName: player.fullName,
        position: player.position,
        allowedPositions: [player.position],
        filter,
      })
    )
    .sort((left, right) =>
      isRound1
        ? right.regSeasonPts - left.regSeasonPts || right.points - left.points
        : right.points - left.points || right.goals - left.goals
    );
}

export function filterTeamRows(params: {
  teamRows: DraftTeamRow[];
  positionFilter: string;
  searchQuery: string;
}): DraftTeamRow[] {
  const { teamRows, positionFilter, searchQuery } = params;
  const filter = buildDraftSearchFilter(positionFilter, searchQuery);
  return teamRows
    .filter((team) =>
      matchesDraftRow({
        fullName: team.fullName,
        position: 'G',
        allowedPositions: ['G'],
        filter,
      })
    )
    .sort(
      (left, right) => right.wins - left.wins || right.shutouts - left.shutouts
    );
}

export function canDraftGoalie(
  mySlotCounts: MySlotCounts,
  roster: DraftRosterComposition
): boolean {
  return mySlotCounts.G < roster.goalies;
}

function isSkaterPosition(position: string | null | undefined): boolean {
  return position != null && SKATER_POSITIONS.has(position);
}

function buildDraftSearchFilter(
  positionFilter: string,
  searchQuery: string
): DraftSearchFilter {
  return {
    positionFilter,
    query: searchQuery.toLowerCase(),
  };
}

function matchesDraftRow(params: {
  fullName: string;
  position: string;
  allowedPositions: string[];
  filter: DraftSearchFilter;
}): boolean {
  const { fullName, position, allowedPositions, filter } = params;
  if (!matchesPositionFilter({ position, allowedPositions, filter })) {
    return false;
  }

  return (
    filter.query.length === 0 || fullName.toLowerCase().includes(filter.query)
  );
}

function matchesPositionFilter(params: {
  position: string;
  allowedPositions: string[];
  filter: DraftSearchFilter;
}): boolean {
  const {
    position,
    allowedPositions,
    filter: { positionFilter },
  } = params;
  if (positionFilter === 'ALL') {
    return true;
  }

  if (positionFilter === position) {
    return true;
  }

  return allowedPositions.includes(positionFilter);
}
