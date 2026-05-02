import { calculateGoaliePoints, calculatePlayerPoints } from '@sportsnot/utils';

interface DraftPlayerStatsRow {
  player_id: number;
  goals: number;
  assists: number;
}

interface DraftTeamStatsRow {
  team_id: number;
  wins: number;
  shutouts: number;
}

const EMPTY_TIMESTAMP = '1970-01-01T00:00:00.000Z';

export function getInitialDraftRosterPoints(params: {
  playerId: number | null;
  teamId: number | null;
  playoffRound: number;
  playerStats: DraftPlayerStatsRow[];
  teamStats: DraftTeamStatsRow[];
}): number {
  if (params.playerId != null) {
    const stats = params.playerStats.find(
      (player) => player.player_id === params.playerId
    );
    if (!stats) {
      return 0;
    }

    return calculatePlayerPoints({
      playerId: params.playerId,
      nhlSeason: '',
      playoffRound: params.playoffRound,
      goals: stats.goals ?? 0,
      assists: stats.assists ?? 0,
      gamesPlayed: 0,
      isInjured: false,
      lastUpdated: EMPTY_TIMESTAMP,
    });
  }

  if (params.teamId != null) {
    const stats = params.teamStats.find(
      (team) => team.team_id === params.teamId
    );
    if (!stats) {
      return 0;
    }

    return calculateGoaliePoints({
      teamId: params.teamId,
      nhlSeason: '',
      playoffRound: params.playoffRound,
      wins: stats.wins ?? 0,
      shutouts: stats.shutouts ?? 0,
      isEliminated: false,
      lastUpdated: EMPTY_TIMESTAMP,
    });
  }

  return 0;
}
