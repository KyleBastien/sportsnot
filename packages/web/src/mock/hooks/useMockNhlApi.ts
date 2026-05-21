import type {
  NHLPlayer,
  NHLTeam,
  NHLGame,
  NHLPlayoffSeries,
  NHLPlayerStats,
} from '@sportsnot/types';
import {
  teams,
  players,
  bracket,
  gamesR1,
  gamesR2,
  gamesCf,
  gamesScf,
  playerGameLogs,
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

const ALL_GAMES: NHLGame[] = [
  ...(gamesR1 as unknown as NHLGame[]),
  ...(gamesR2 as unknown as NHLGame[]),
  ...(gamesCf as unknown as NHLGame[]),
  ...(gamesScf as unknown as NHLGame[]),
];

const ROUND_GAMES: Record<number, NHLGame[]> = {
  1: gamesR1 as unknown as NHLGame[],
  2: gamesR2 as unknown as NHLGame[],
  3: gamesCf as unknown as NHLGame[],
  4: gamesScf as unknown as NHLGame[],
};

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

export function useMockCumulativePlayoffPlayers(
  _season: string,
  round: number
) {
  const throughDate = getRoundLastDate(round);
  const cumulativeStats = getCumulativePlayerStats(throughDate);
  const allPlayers = Object.entries(players).flatMap(([teamAbbr, roster]) =>
    roster
      .filter((player) => player.primaryPosition.type !== 'Goalie')
      .map((player) => {
        const stats = cumulativeStats.get(player.id);
        return {
          player_id: player.id,
          player_name: player.fullName,
          position: player.primaryPosition.type === 'Forward' ? 'F' : 'D',
          team_abbreviation: teamAbbr,
          is_injured: false,
          goals: stats?.goals ?? 0,
          assists: stats?.assists ?? 0,
          games_played: stats?.games_played ?? 0,
          nhl_season: _season,
          playoff_round: round,
        };
      })
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

export function useMockCumulativePlayoffTeams(_season: string, round: number) {
  const throughDate = getRoundLastDate(round);
  const cumulativeStats = getCumulativeTeamStats(throughDate);
  const allTeams = teams.map((team) => {
    const stats = cumulativeStats.get(team.id);
    return {
      team_id: team.id,
      team_name: team.name,
      team_abbreviation: team.abbreviation,
      is_eliminated: false,
      wins: stats?.wins ?? 0,
      shutouts: stats?.shutouts ?? 0,
      nhl_season: _season,
      playoff_round: round,
    };
  });

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

function getRoundLastDate(round: number): string | null {
  const games = ROUND_GAMES[round] ?? [];
  if (games.length === 0) {
    return null;
  }

  return (
    [...games]
      .map((game) => game.gameDate)
      .sort()
      .at(-1) ?? null
  );
}

function getCumulativePlayerStats(throughDate: string | null) {
  const totals = new Map<
    number,
    { goals: number; assists: number; games_played: number }
  >();

  if (!throughDate) {
    return totals;
  }

  for (const [playerId, entries] of Object.entries(
    playerGameLogs as Record<string, NHLPlayerStats[]>
  )) {
    for (const entry of entries) {
      if (entry.gameDate > throughDate) {
        continue;
      }

      const numericPlayerId = Number(playerId);
      const current = totals.get(numericPlayerId) ?? {
        goals: 0,
        assists: 0,
        games_played: 0,
      };
      current.goals += entry.goals;
      current.assists += entry.assists;
      current.games_played += 1;
      totals.set(numericPlayerId, current);
    }
  }

  return totals;
}

function getCumulativeTeamStats(throughDate: string | null) {
  const totals = new Map<number, { wins: number; shutouts: number }>();

  if (!throughDate) {
    return totals;
  }

  for (const game of ALL_GAMES) {
    applyTeamGameTotals(totals, game, throughDate);
  }

  return totals;
}

function applyTeamGameTotals(
  totals: Map<number, { wins: number; shutouts: number }>,
  game: NHLGame,
  throughDate: string
) {
  if (game.gameDate > throughDate) {
    return;
  }

  seedTeamTotals(totals, game.homeTeam.id);
  seedTeamTotals(totals, game.awayTeam.id);

  const winner = getWinningTeamResult(game);
  if (!winner) {
    return;
  }

  const winningTotals = totals.get(winner.teamId);
  if (!winningTotals) {
    return;
  }

  winningTotals.wins += 1;
  winningTotals.shutouts += Number(winner.isShutout);
}

function getWinningTeamResult(game: NHLGame) {
  const homeScore = game.homeTeam.score ?? 0;
  const awayScore = game.awayTeam.score ?? 0;
  if (homeScore === awayScore) {
    return null;
  }

  return homeScore > awayScore
    ? { teamId: game.homeTeam.id, isShutout: awayScore === 0 }
    : { teamId: game.awayTeam.id, isShutout: homeScore === 0 };
}

function seedTeamTotals(
  totals: Map<number, { wins: number; shutouts: number }>,
  teamId: number
) {
  if (!totals.has(teamId)) {
    totals.set(teamId, { wins: 0, shutouts: 0 });
  }
}
