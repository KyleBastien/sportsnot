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
  regularSeasonStats,
} from '@sportsnot/mock-data';

/**
 * Returns abbreviations of teams eliminated in rounds before `beforeRound`.
 * For round 1, returns empty set (all teams alive).
 * For round 2, returns teams eliminated in round 1, etc.
 */
export function getEliminatedAbbreviations(beforeRound: number): Set<string> {
  const eliminated = new Set<string>();
  for (const series of bracket) {
    if (series.round >= beforeRound) continue;
    if (!series.topSeedTeam || !series.bottomSeedTeam) continue;
    const topWins = series.topSeedWins ?? 0;
    const bottomWins = series.bottomSeedWins ?? 0;
    if (topWins === 4 && series.bottomSeedTeam.abbreviation) {
      eliminated.add(series.bottomSeedTeam.abbreviation);
    } else if (bottomWins === 4 && series.topSeedTeam.abbreviation) {
      eliminated.add(series.topSeedTeam.abbreviation);
    }
  }
  return eliminated;
}

// ── Mock NHL API functions ─────────────────────────────────────────────
// These mirror the signatures in @sportsnot/nhl-api but return fixture data.

export async function mockGetPlayoffBracket(
  _season: string
): Promise<NHLPlayoffSeries[]> {
  return [...bracket];
}

export async function mockGetTeamRoster(
  teamAbbreviation: string,

  _season: string
): Promise<NHLPlayer[]> {
  return [
    ...((players as Record<string, readonly NHLPlayer[]>)[teamAbbreviation] ??
      []),
  ];
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
 * Filters out players from teams eliminated before the given round.
 */
export function useMockPlayoffPlayers(_season: string, round: number) {
  const eliminatedAbbrs = getEliminatedAbbreviations(round);
  const allPlayers = Object.entries(players)
    .filter(([teamAbbr]) => !eliminatedAbbrs.has(teamAbbr))
    .flatMap(([teamAbbr, roster]) =>
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
          playoff_round: round,
        }))
    );

  return makeMockQuery(allPlayers);
}

/**
 * Mock replacement for usePlayoffTeams from @sportsnot/supabase.
 * Returns team stats in the same shape as the team_stats_cache table.
 * Filters out teams eliminated before the given round.
 */
export function useMockPlayoffTeams(_season: string, round: number) {
  const eliminatedAbbrs = getEliminatedAbbreviations(round);
  const allTeams = teams
    .filter((t) => !eliminatedAbbrs.has(t.abbreviation))
    .map((t) => ({
      team_id: t.id,
      team_name: t.name,
      team_abbreviation: t.abbreviation,
      is_eliminated: false,
      wins: 0,
      shutouts: 0,
      nhl_season: _season,
      playoff_round: round,
    }));

  return makeMockQuery(allTeams);
}

/**
 * Mock replacement for useRegularSeasonPlayers from @sportsnot/supabase.
 * Returns regular season stats for all skaters from the fixture data.
 * Only returns data when enabled is true (mirrors the real hook).
 */
export function useMockRegularSeasonPlayers(_season: string, enabled: boolean) {
  if (!enabled) {
    return makeMockQuery(
      [] as Array<{
        player_id: number;
        player_name: string;
        position: string;
        team_abbreviation: string;
        goals: number;
        assists: number;
        points: number;
        games_played: number;
        nhl_season: string;
      }>
    );
  }

  const allPlayers = Object.entries(players).flatMap(([teamAbbr, roster]) =>
    roster
      .filter((p) => p.primaryPosition.type !== 'Goalie')
      .map((p) => {
        const stats = regularSeasonStats[String(p.id)];
        return {
          player_id: p.id,
          player_name: p.fullName,
          position: p.primaryPosition.type === 'Forward' ? 'F' : 'D',
          team_abbreviation: teamAbbr,
          goals: stats?.goals ?? 0,
          assists: stats?.assists ?? 0,
          points: stats?.points ?? 0,
          games_played: stats?.gamesPlayed ?? 0,
          nhl_season: _season,
        };
      })
  );

  return makeMockQuery(allPlayers);
}
