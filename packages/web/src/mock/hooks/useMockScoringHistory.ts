import { useMockData } from '../MockDataProvider';
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

// ── ScoringEvent interface (matches ScoringHistoryPage.tsx) ────────────
interface ScoringEvent {
  id: string;
  player_name: string;
  team_abbreviation: string;
  event_type: 'goal' | 'assist' | 'win' | 'shutout';
  points: number;
  game_date: string;
  league_member_team: string;
}

// ── useMockScoringHistory ──────────────────────────────────────────────
// Returns ScoringEvent[] matching the inline useScoringHistory hook in ScoringHistoryPage.tsx
export function useMockScoringHistory(leagueId: string) {
  const { state } = useMockData();

  const league = state.leagues.find((l) => l.id === leagueId);
  if (!league) {
    return makeMockQuery([] as ScoringEvent[]);
  }

  const events: ScoringEvent[] = [];
  const logs = playerGameLogs as unknown as Record<number, NHLPlayerStats[]>;

  for (const member of league.members) {
    const roster = state.rosters[member.id] ?? [];
    const activePlayers = roster.filter((s) => s.isActive && s.playerId);

    for (const slot of activePlayers) {
      const playerId = slot.playerId!;
      const info = getPlayerInfo(playerId);
      if (!info) continue;

      const entries = logs[playerId] ?? [];

      for (const entry of entries) {
        if (entry.gameDate > state.simulationDate) continue;

        if (info.isGoalie) {
          // Goalie scoring events: win or shutout
          const game = GAME_MAP.get(entry.gameId);
          if (game) {
            const isHome = game.homeTeam.abbreviation === entry.teamAbbrev;
            const teamScore = isHome ? (game.homeTeam.score ?? 0) : (game.awayTeam.score ?? 0);
            const oppScore = isHome ? (game.awayTeam.score ?? 0) : (game.homeTeam.score ?? 0);
            if (teamScore > oppScore) {
              if (oppScore === 0) {
                events.push({
                  id: `${entry.gameId}-${playerId}-shutout`,
                  player_name: info.name,
                  team_abbreviation: info.teamAbbrev,
                  event_type: 'shutout',
                  points: SCORING.shutout,
                  game_date: entry.gameDate,
                  league_member_team: member.teamName,
                });
              } else {
                events.push({
                  id: `${entry.gameId}-${playerId}-win`,
                  player_name: info.name,
                  team_abbreviation: info.teamAbbrev,
                  event_type: 'win',
                  points: SCORING.win,
                  game_date: entry.gameDate,
                  league_member_team: member.teamName,
                });
              }
            }
          }
        } else {
          // Skater scoring events: individual goals and assists
          for (let i = 0; i < entry.goals; i++) {
            events.push({
              id: `${entry.gameId}-${playerId}-goal-${i}`,
              player_name: info.name,
              team_abbreviation: info.teamAbbrev,
              event_type: 'goal',
              points: SCORING.goal,
              game_date: entry.gameDate,
              league_member_team: member.teamName,
            });
          }
          for (let i = 0; i < entry.assists; i++) {
            events.push({
              id: `${entry.gameId}-${playerId}-assist-${i}`,
              player_name: info.name,
              team_abbreviation: info.teamAbbrev,
              event_type: 'assist',
              points: SCORING.assist,
              game_date: entry.gameDate,
              league_member_team: member.teamName,
            });
          }
        }
      }
    }
  }

  // Sort by game_date descending (most recent first)
  events.sort((a, b) => b.game_date.localeCompare(a.game_date));

  return makeMockQuery(events);
}
