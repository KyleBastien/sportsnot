import type {
  NHLPlayer,
  NHLTeam,
  NHLGame,
  NHLPlayoffSeries,
} from '@sportsnot/types';
import {
  teams,
  players,
  bracket,
  gamesR1,
  gamesR2,
  gamesCf,
  gamesScf,
} from '@sportsnot/mock-data';

// ── Mock NHL API functions ─────────────────────────────────────────────
// These mirror the signatures in @sportsnot/nhl-api but return fixture data.

export async function mockGetPlayoffBracket(
  // eslint-disable-next-line no-unused-vars
  _season: string
): Promise<NHLPlayoffSeries[]> {
  return [...bracket];
}

export async function mockGetTeamRoster(
  teamAbbreviation: string,
  // eslint-disable-next-line no-unused-vars
  _season: string
): Promise<NHLPlayer[]> {
  return [...(players[teamAbbreviation] ?? [])];
}

export async function mockGetPlayer(playerId: number): Promise<NHLPlayer> {
  for (const roster of Object.values(players)) {
    const found = roster.find((p) => p.id === playerId);
    if (found) return { ...found };
  }
  throw new Error(`Mock player not found: ${playerId}`);
}

export async function mockGetTeams(): Promise<NHLTeam[]> {
  return [...teams];
}

export async function mockGetPlayoffSchedule(
  // eslint-disable-next-line no-unused-vars
  _season: string
): Promise<NHLGame[]> {
  return [
    ...(gamesR1 as unknown as NHLGame[]),
    ...(gamesR2 as unknown as NHLGame[]),
    ...(gamesCf as unknown as NHLGame[]),
    ...(gamesScf as unknown as NHLGame[]),
  ];
}

// ── Mock TanStack Query-shaped hooks ───────────────────────────────────
// These return the same shape as UseQueryResult so components can
// destructure { data, isLoading, error } without code changes.

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

/**
 * Mock replacement for usePlayoffPlayers from @sportsnot/supabase.
 * Returns player stats in the same shape as the player_stats_cache table.
 */
export function useMockPlayoffPlayers(_season: string, _round: number) {
  const allPlayers = Object.entries(players).flatMap(([teamAbbr, roster]) =>
    roster
      .filter((p) => p.primaryPosition.type !== 'Goalie')
      .map((p) => ({
        player_id: p.id,
        player_name: p.fullName,
        position: p.primaryPosition.type === 'Forward' ? 'F' : 'D',
        team_abbreviation: teamAbbr,
        is_injured: false,
        goals: 0,
        assists: 0,
        games_played: 0,
        nhl_season: _season,
        playoff_round: _round,
      }))
  );

  return makeMockQuery(allPlayers);
}

/**
 * Mock replacement for usePlayoffTeams from @sportsnot/supabase.
 * Returns team stats in the same shape as the team_stats_cache table.
 */
export function useMockPlayoffTeams(_season: string, _round: number) {
  const allTeams = teams.map((t) => ({
    team_id: t.id,
    team_name: t.name,
    team_abbreviation: t.abbreviation,
    is_eliminated: false,
    wins: 0,
    shutouts: 0,
    nhl_season: _season,
    playoff_round: _round,
  }));

  return makeMockQuery(allTeams);
}
