import { useMockData, getRoundDateBounds } from '../MockDataProvider';
import { SCORING } from '@sportsnot/types';
import { playerGameLogs, players, gamesR1, gamesR2, gamesCf, gamesScf } from '@sportsnot/mock-data';
import type { NHLPlayerStats, NHLGame, NHLPlayer } from '@sportsnot/types';

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

// ── Player info lookup ─────────────────────────────────────────────────
const allPlayers = players as unknown as Record<string, NHLPlayer[]>;

function getPlayerInfo(playerId: number): { name: string; teamAbbrev: string; isGoalie: boolean } | null {
  for (const [teamAbbrev, teamPlayers] of Object.entries(allPlayers)) {
    const p = teamPlayers.find((pl) => pl.id === playerId);
    if (p) {
      return {
        name: p.fullName,
        teamAbbrev,
        isGoalie: p.primaryPosition.type === 'Goalie',
      };
    }
  }
  return null;
}

// ── Game lookup for goalie win/shutout determination ───────────────────
const ALL_GAMES: NHLGame[] = [
  ...(gamesR1 as unknown as NHLGame[]),
  ...(gamesR2 as unknown as NHLGame[]),
  ...(gamesCf as unknown as NHLGame[]),
  ...(gamesScf as unknown as NHLGame[]),
];

const GAME_MAP = new Map<number, NHLGame>();
for (const g of ALL_GAMES) {
  GAME_MAP.set(g.id, g);
}

// ── Points calculation per member ──────────────────────────────────────
function calculateMemberPoints(
  playerIds: number[],
  throughDate: string,
): { total: number; playerPts: number; goaliePts: number; roundPts: Record<number, number> } {
  let playerPts = 0;
  let goaliePts = 0;
  const roundPts: Record<number, number> = {};

  const logs = playerGameLogs as unknown as Record<number, NHLPlayerStats[]>;

  for (const playerId of playerIds) {
    const entries = logs[playerId] ?? [];
    const info = getPlayerInfo(playerId);
    const isGoalie = info?.isGoalie ?? false;

    for (const entry of entries) {
      if (entry.gameDate > throughDate) continue;

      let entryPoints = 0;

      if (isGoalie) {
        const game = GAME_MAP.get(entry.gameId);
        if (game) {
          const isHome = game.homeTeam.abbreviation === entry.teamAbbrev;
          const teamScore = isHome ? (game.homeTeam.score ?? 0) : (game.awayTeam.score ?? 0);
          const oppScore = isHome ? (game.awayTeam.score ?? 0) : (game.homeTeam.score ?? 0);
          if (teamScore > oppScore) {
            // Shutout replaces win points
            entryPoints = oppScore === 0 ? SCORING.shutout : SCORING.win;
          }
        }
        goaliePts += entryPoints;
      } else {
        entryPoints = entry.goals * SCORING.goal + entry.assists * SCORING.assist;
        playerPts += entryPoints;
      }

      // Assign to the appropriate round bucket
      if (entryPoints > 0) {
        for (let r = 1; r <= 4; r++) {
          const bounds = getRoundDateBounds(r);
          if (bounds && entry.gameDate >= bounds.firstDate && entry.gameDate <= bounds.lastDate) {
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

    const pts = calculateMemberPoints(activePlayerIds, state.simulationDate);

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
