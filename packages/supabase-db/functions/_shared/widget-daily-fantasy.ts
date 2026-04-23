import { calculateGoalieGamePoints, calculatePlayerPoints } from './scoring.ts';

export interface WidgetDailyFantasyPlayer {
  playerId: number;
  goals?: number;
  assists?: number;
}

export interface WidgetDailyFantasyTeamStats {
  forwards?: WidgetDailyFantasyPlayer[];
  defense?: WidgetDailyFantasyPlayer[];
  goalies?: WidgetDailyFantasyPlayer[];
}

export interface WidgetDailyFantasyGame {
  id: number;
  state: string;
  homeTeam: {
    id: number;
    score?: number;
  };
  awayTeam: {
    id: number;
    score?: number;
  };
}

export interface WidgetDailyFantasyBoxscore {
  playerByGameStats?: {
    homeTeam?: WidgetDailyFantasyTeamStats;
    awayTeam?: WidgetDailyFantasyTeamStats;
  };
}

export interface WidgetDailyFantasyPointMaps {
  playerDailyPointsById: Map<number, number>;
  teamDailyPointsById: Map<number, number>;
}

export function buildDailyFantasyPointMaps(
  games: WidgetDailyFantasyGame[],
  boxscoresByGameId: Map<number, WidgetDailyFantasyBoxscore>
): WidgetDailyFantasyPointMaps {
  const playerDailyPointsById = new Map<number, number>();
  const teamDailyPointsById = new Map<number, number>();

  for (const game of games) {
    const boxscore = boxscoresByGameId.get(game.id);
    if (boxscore) {
      accumulateTeamStats(
        playerDailyPointsById,
        boxscore.playerByGameStats?.homeTeam
      );
      accumulateTeamStats(
        playerDailyPointsById,
        boxscore.playerByGameStats?.awayTeam
      );
    }

    if (isFinalWidgetGameState(game.state)) {
      const homeScore = game.homeTeam.score ?? 0;
      const awayScore = game.awayTeam.score ?? 0;
      teamDailyPointsById.set(
        game.homeTeam.id,
        calculateGoalieGamePoints(homeScore, awayScore)
      );
      teamDailyPointsById.set(
        game.awayTeam.id,
        calculateGoalieGamePoints(awayScore, homeScore)
      );
      continue;
    }

    teamDailyPointsById.set(game.homeTeam.id, 0);
    teamDailyPointsById.set(game.awayTeam.id, 0);
  }

  return {
    playerDailyPointsById,
    teamDailyPointsById,
  };
}

export function isFinalWidgetGameState(state: string): boolean {
  return state === 'FINAL' || state === 'OFF';
}

function accumulateTeamStats(
  playerDailyPointsById: Map<number, number>,
  stats: WidgetDailyFantasyTeamStats | undefined
) {
  const players = [
    ...(stats?.forwards ?? []),
    ...(stats?.defense ?? []),
    ...(stats?.goalies ?? []),
  ];

  for (const player of players) {
    if (!player?.playerId) continue;
    const delta = calculatePlayerPoints({
      goals: player.goals ?? 0,
      assists: player.assists ?? 0,
    });
    const current = playerDailyPointsById.get(player.playerId) ?? 0;
    playerDailyPointsById.set(player.playerId, current + delta);
  }
}
