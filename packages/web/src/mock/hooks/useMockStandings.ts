import { useMockData, getRoundDateBounds } from '../MockDataProvider';
import { SCORING } from '@sportsnot/types';
import {
  playerGameLogs,
  gamesR1,
  gamesR2,
  gamesCf,
  gamesScf,
} from '@sportsnot/mock-data';
import type { NHLPlayerStats, NHLGame } from '@sportsnot/types';

// ── Mock TanStack query helper ─────────────────────────────────────────
interface MockQueryResult<T> {
  data: T;
  isLoading: false;
  isError: false;
  error: null;
  isFetching: false;
  isSuccess: true;
  status: 'success';
  refetch: () => Promise<MockQueryResult<T>>;
}

function makeMockQuery<T>(data: T): MockQueryResult<T> {
  const result: MockQueryResult<T> = {
    data,
    isLoading: false,
    isError: false,
    error: null,
    isFetching: false,
    isSuccess: true,
    status: 'success',
    refetch: () => Promise.resolve(result),
  };
  return result;
}

// ── Game lookup for goalie win/shutout determination ───────────────────
const ALL_GAMES: NHLGame[] = [
  ...(gamesR1 as unknown as NHLGame[]),
  ...(gamesR2 as unknown as NHLGame[]),
  ...(gamesCf as unknown as NHLGame[]),
  ...(gamesScf as unknown as NHLGame[]),
];

// ── Points calculation per member per round ────────────────────────────
function calculateRoundMemberPoints(
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

// ── useMockStandings ───────────────────────────────────────────────────
// Returns data matching the inline useStandings hook in StandingsPage.tsx:
// { league: { name, current_round }, members: [{ id, user_id, team_name, total_points, ... }] }
export function useMockStandings(leagueId: string) {
  const { state } = useMockData();

  const league = state.leagues.find((l) => l.id === leagueId);
  if (!league) {
    return makeMockQuery({ league: null, members: [] });
  }

  const members = league.members.map((member) => {
    let totalPlayerPts = 0;
    let totalGoaliePts = 0;
    const roundPts: Record<number, number> = {};

    // Calculate points per round using each round's actual roster
    for (let r = 1; r <= state.currentRound; r++) {
      const bounds = getRoundDateBounds(r);
      if (!bounds) continue;

      // Use rosterHistory for past rounds, current rosters for current round
      const roster =
        r < state.currentRound
          ? (state.rosterHistory[member.id]?.[r] ?? [])
          : (state.rosters[member.id] ?? []);

      const activePlayerIds = roster
        .filter((s) => s.isActive && s.playerId)
        .map((s) => s.playerId!);
      const goalieTeamIds = roster
        .filter((s) => s.isActive && s.teamId && !s.playerId)
        .map((s) => s.teamId!);

      // Cap through-date to the earlier of simulation date or round end
      const throughDate =
        state.simulationDate < bounds.lastDate
          ? state.simulationDate
          : bounds.lastDate;

      if (state.simulationDate < bounds.firstDate) continue;

      const pts = calculateRoundMemberPoints(
        activePlayerIds,
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
      id: member.id,
      user_id: member.userId,
      team_name: member.teamName,
      total_points: totalPlayerPts + totalGoaliePts,
      player_points: totalPlayerPts,
      goalie_points: totalGoaliePts,
      round_points: roundPts,
      users: { display_name: member.user?.displayName ?? 'Unknown' },
    };
  });

  // Sort by total_points descending
  members.sort((a, b) => b.total_points - a.total_points);

  return makeMockQuery({
    league: { name: league.name, current_round: state.currentRound },
    members,
  });
}
