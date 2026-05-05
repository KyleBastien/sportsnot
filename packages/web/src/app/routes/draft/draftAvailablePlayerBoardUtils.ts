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

export function shouldUseRegSeasonFallback(
  isRound1: boolean,
  playerStats: PlayerStatRow[]
): boolean {
  return (
    isRound1 &&
    (playerStats.length === 0 ||
      playerStats.every((player) => (player.games_played ?? 0) === 0))
  );
}

export function buildSkaterRows(params: {
  playerStats: PlayerStatRow[];
  regSeasonStats: RegSeasonStatRow[];
  draftedPlayerIds: Set<number>;
  isRound1: boolean;
}): DraftSkaterRow[] {
  const { playerStats, regSeasonStats, draftedPlayerIds, isRound1 } = params;
  const regSeasonMap = new Map(
    regSeasonStats.map((row) => [row.player_id, row])
  );

  if (shouldUseRegSeasonFallback(isRound1, playerStats)) {
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
        goals: player.goals ?? 0,
        assists: player.assists ?? 0,
        points: (player.goals ?? 0) + (player.assists ?? 0),
        gamesPlayed: player.games_played ?? 0,
        regSeasonPts: regSeason?.points ?? 0,
      };
    });
}

export function buildTeamRows(
  teamStats: TeamStatRow[],
  draftedTeamIds: Set<number>
): DraftTeamRow[] {
  return teamStats
    .filter((team) => !draftedTeamIds.has(team.team_id))
    .filter((team) => !team.is_eliminated)
    .map((team) => ({
      id: team.team_id,
      fullName: team.team_name ?? `Team #${team.team_id}`,
      team: team.team_abbreviation ?? `Team #${team.team_id}`,
      teamId: team.team_id,
      wins: team.wins ?? 0,
      shutouts: team.shutouts ?? 0,
    }));
}

export function filterSkaterRows(
  skaterRows: DraftSkaterRow[],
  positionFilter: string,
  searchQuery: string,
  isRound1: boolean
): DraftSkaterRow[] {
  const query = searchQuery.toLowerCase();
  return skaterRows
    .filter((player) => matchesSkaterFilter(player, positionFilter, query))
    .sort((left, right) =>
      isRound1
        ? right.regSeasonPts - left.regSeasonPts || right.points - left.points
        : right.points - left.points || right.goals - left.goals
    );
}

export function filterTeamRows(
  teamRows: DraftTeamRow[],
  positionFilter: string,
  searchQuery: string
): DraftTeamRow[] {
  const query = searchQuery.toLowerCase();
  return teamRows
    .filter((team) => matchesTeamFilter(team, positionFilter, query))
    .sort((left, right) => right.wins - left.wins);
}

export function canDraftGoalie(
  mySlotCounts: MySlotCounts,
  roster: DraftRosterComposition
): boolean {
  return mySlotCounts.G < roster.goalies;
}

function isSkaterPosition(position: string | null | undefined): boolean {
  return position === 'F' || position === 'D';
}

function matchesSkaterFilter(
  player: DraftSkaterRow,
  positionFilter: string,
  query: string
): boolean {
  if (!matchesPositionFilter(player.position, positionFilter)) {
    return false;
  }

  return query.length === 0 || player.fullName.toLowerCase().includes(query);
}

function matchesTeamFilter(
  team: DraftTeamRow,
  positionFilter: string,
  query: string
): boolean {
  if (positionFilter !== 'ALL' && positionFilter !== 'G') {
    return false;
  }

  return query.length === 0 || team.fullName.toLowerCase().includes(query);
}

function matchesPositionFilter(
  position: string,
  positionFilter: string
): boolean {
  if (positionFilter === 'ALL') {
    return true;
  }

  return positionFilter === position;
}
