import { SCORING } from '@sportsnot/types';
import type { NHLPlayerStats, NHLGame, RosterSlot } from '@sportsnot/types';
import {
  playerGameLogs,
  gamesR1,
  gamesR2,
  gamesCf,
  gamesScf,
} from '@sportsnot/mock-data';
import { getRoundDateBounds, type MockState } from './MockDataProvider';

export function isMockMode(): boolean {
  return import.meta.env.VITE_MOCK_MODE === 'true';
}

// ── Game lookup for goalie win/shutout determination ───────────────────
const ALL_GAMES: NHLGame[] = [
  ...(gamesR1 as unknown as NHLGame[]),
  ...(gamesR2 as unknown as NHLGame[]),
  ...(gamesCf as unknown as NHLGame[]),
  ...(gamesScf as unknown as NHLGame[]),
];

/**
 * Calculate points for a set of players/goalies within a date range.
 */
export function calculateRoundMemberPoints(
  playerIds: number[],
  goalieTeamIds: number[],
  fromDate: string,
  throughDate: string
): { playerPts: number; goaliePts: number } {
  let playerPts = 0;
  let goaliePts = 0;

  const logs = playerGameLogs as unknown as Record<number, NHLPlayerStats[]>;

  for (const playerId of playerIds) {
    const entries = logs[playerId] ?? [];
    for (const entry of entries) {
      if (entry.gameDate < fromDate || entry.gameDate > throughDate) continue;
      playerPts += entry.goals * SCORING.goal + entry.assists * SCORING.assist;
    }
  }

  for (const teamId of goalieTeamIds) {
    for (const game of ALL_GAMES) {
      if (game.gameDate < fromDate || game.gameDate > throughDate) continue;

      const isHome = game.homeTeam.id === teamId;
      const isAway = game.awayTeam.id === teamId;
      if (!isHome && !isAway) continue;

      const teamScore = isHome
        ? (game.homeTeam.score ?? 0)
        : (game.awayTeam.score ?? 0);
      const oppScore = isHome
        ? (game.awayTeam.score ?? 0)
        : (game.homeTeam.score ?? 0);

      if (teamScore > oppScore) {
        goaliePts += oppScore === 0 ? SCORING.shutout : SCORING.win;
      }
    }
  }

  return { playerPts, goaliePts };
}

/**
 * Extract active player IDs and goalie team IDs from roster slots.
 */
function extractRosterIds(roster: RosterSlot[]): {
  playerIds: number[];
  goalieTeamIds: number[];
} {
  const playerIds = roster
    .filter((s) => s.isActive && s.playerId)
    .map((s) => s.playerId!);
  const goalieTeamIds = roster
    .filter((s) => s.isActive && s.teamId && !s.playerId)
    .map((s) => s.teamId!);
  return { playerIds, goalieTeamIds };
}

export interface MemberPointsResult {
  totalPoints: number;
  playerPoints: number;
  goaliePoints: number;
  roundPoints: Record<number, number>;
}

/**
 * Calculate cumulative points for a league member across all rounds
 * up to the current simulation state.
 */
export function calculateMemberPoints(
  state: Pick<
    MockState,
    'currentRound' | 'simulationDate' | 'rosters' | 'rosterHistory'
  >,
  memberId: string
): MemberPointsResult {
  let totalPlayerPts = 0;
  let totalGoaliePts = 0;
  const roundPts: Record<number, number> = {};

  for (let r = 1; r <= state.currentRound; r++) {
    const bounds = getRoundDateBounds(r);
    if (!bounds) continue;

    const roster =
      r < state.currentRound
        ? (state.rosterHistory[memberId]?.[r] ?? [])
        : (state.rosters[memberId] ?? []);

    const { playerIds, goalieTeamIds } = extractRosterIds(roster);

    const throughDate =
      state.simulationDate < bounds.lastDate
        ? state.simulationDate
        : bounds.lastDate;

    if (state.simulationDate < bounds.firstDate) continue;

    const pts = calculateRoundMemberPoints(
      playerIds,
      goalieTeamIds,
      bounds.firstDate,
      throughDate
    );

    totalPlayerPts += pts.playerPts;
    totalGoaliePts += pts.goaliePts;
    const roundTotal = pts.playerPts + pts.goaliePts;
    if (roundTotal > 0) {
      roundPts[r] = roundTotal;
    }
  }

  return {
    totalPoints: totalPlayerPts + totalGoaliePts,
    playerPoints: totalPlayerPts,
    goaliePoints: totalGoaliePts,
    roundPoints: roundPts,
  };
}
