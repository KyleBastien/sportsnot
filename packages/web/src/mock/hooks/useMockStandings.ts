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

// ── Points calculation per member ──────────────────────────────────────
function calculateMemberPoints(
  playerIds: number[],
  goalieTeamIds: number[],
  throughDate: string
): {
  total: number;
  playerPts: number;
  goaliePts: number;
  roundPts: Record<number, number>;
} {
  let playerPts = 0;
  let goaliePts = 0;
  const roundPts: Record<number, number> = {};

  const logs = playerGameLogs as unknown as Record<number, NHLPlayerStats[]>;

  // Skater points from player game logs
  for (const playerId of playerIds) {
    const entries = logs[playerId] ?? [];

    for (const entry of entries) {
      if (entry.gameDate > throughDate) continue;

      const entryPoints =
        entry.goals * SCORING.goal + entry.assists * SCORING.assist;
      playerPts += entryPoints;

      if (entryPoints > 0) {
        for (let r = 1; r <= 4; r++) {
          const bounds = getRoundDateBounds(r);
          if (
            bounds &&
            entry.gameDate >= bounds.firstDate &&
            entry.gameDate <= bounds.lastDate
          ) {
            roundPts[r] = (roundPts[r] ?? 0) + entryPoints;
            break;
          }
        }
      }
    }
  }

  // Goalie points from team game results
  for (const teamId of goalieTeamIds) {
    for (const game of ALL_GAMES) {
      if (game.gameDate > throughDate) continue;

      const isHome = game.homeTeam.id === teamId;
      const isAway = game.awayTeam.id === teamId;
      if (!isHome && !isAway) continue;

      const teamScore = isHome
        ? (game.homeTeam.score ?? 0)
        : (game.awayTeam.score ?? 0);
      const oppScore = isHome
        ? (game.awayTeam.score ?? 0)
        : (game.homeTeam.score ?? 0);

      let entryPoints = 0;
      if (teamScore > oppScore) {
        entryPoints = oppScore === 0 ? SCORING.shutout : SCORING.win;
      }

      goaliePts += entryPoints;

      if (entryPoints > 0) {
        for (let r = 1; r <= 4; r++) {
          const bounds = getRoundDateBounds(r);
          if (
            bounds &&
            game.gameDate >= bounds.firstDate &&
            game.gameDate <= bounds.lastDate
          ) {
            roundPts[r] = (roundPts[r] ?? 0) + entryPoints;
            break;
          }
        }
      }
    }
  }

  return { total: playerPts + goaliePts, playerPts, goaliePts, roundPts };
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
    const roster = state.rosters[member.id] ?? [];
    const activePlayerIds = roster
      .filter((s) => s.isActive && s.playerId)
      .map((s) => s.playerId!);
    const goalieTeamIds = roster
      .filter((s) => s.isActive && s.teamId && !s.playerId)
      .map((s) => s.teamId!);

    const pts = calculateMemberPoints(
      activePlayerIds,
      goalieTeamIds,
      state.simulationDate
    );

    return {
      id: member.id,
      user_id: member.userId,
      team_name: member.teamName,
      total_points: pts.total,
      player_points: pts.playerPts,
      goalie_points: pts.goaliePts,
      round_points: pts.roundPts,
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
