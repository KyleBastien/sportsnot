import type { NHLGame } from '@sportsnot/types';
import {
  gamesR1,
  gamesR2,
  gamesCf,
  gamesScf,
  bracket,
} from '@sportsnot/mock-data';
import { useMockData } from '../MockDataProvider';

// ── All fixture games by round ─────────────────────────────────────────
const ROUND_GAMES: Record<number, NHLGame[]> = {
  1: gamesR1 as unknown as NHLGame[],
  2: gamesR2 as unknown as NHLGame[],
  3: gamesCf as unknown as NHLGame[],
  4: gamesScf as unknown as NHLGame[],
};

const ALL_GAMES: NHLGame[] = [
  ...(gamesR1 as unknown as NHLGame[]),
  ...(gamesR2 as unknown as NHLGame[]),
  ...(gamesCf as unknown as NHLGame[]),
  ...(gamesScf as unknown as NHLGame[]),
];

// ── Series status helpers ──────────────────────────────────────────────

/** Make a deterministic key for a matchup (sorted team IDs). */
function seriesKey(teamA: number, teamB: number): string {
  return [teamA, teamB].sort((a, b) => a - b).join('-');
}

interface SeriesStatus {
  homeWins: number;
  awayWins: number;
  label: string; // e.g. "FLA leads 2-1" or "Series tied 1-1"
}

/**
 * Compute series status between two teams for a given round
 * based on all games played through `throughDate`.
 */
function computeSeriesStatus(
  round: number,
  homeTeamId: number,
  awayTeamId: number,
  throughDate: string
): SeriesStatus {
  const roundGames = ROUND_GAMES[round] ?? [];
  const key = seriesKey(homeTeamId, awayTeamId);

  let teamAWins = 0; // lower-id team
  let teamBWins = 0; // higher-id team
  const [teamAId] = [homeTeamId, awayTeamId].sort((a, b) => a - b);

  for (const g of roundGames) {
    if (g.gameDate > throughDate) continue;
    if (seriesKey(g.homeTeam.id, g.awayTeam.id) !== key) continue;

    const homeScore = g.homeTeam.score ?? 0;
    const awayScore = g.awayTeam.score ?? 0;
    if (homeScore === awayScore) continue; // skip ties (shouldn't exist in playoffs)

    const winnerId = homeScore > awayScore ? g.homeTeam.id : g.awayTeam.id;
    if (winnerId === teamAId) teamAWins++;
    else teamBWins++;
  }

  // Map back to home/away of the current game
  const homeWins = homeTeamId === teamAId ? teamAWins : teamBWins;
  const awayWins = homeTeamId === teamAId ? teamBWins : teamAWins;

  // Build label using abbreviations from bracket or game data
  const homeAbbr = getTeamAbbr(homeTeamId);
  const awayAbbr = getTeamAbbr(awayTeamId);

  let label: string;
  if (homeWins === awayWins) {
    label =
      homeWins === 0
        ? 'Series not started'
        : `Series tied ${homeWins}-${awayWins}`;
  } else if (homeWins > awayWins) {
    label = `${homeAbbr} leads ${homeWins}-${awayWins}`;
  } else {
    label = `${awayAbbr} leads ${awayWins}-${homeWins}`;
  }

  return { homeWins, awayWins, label };
}

/** Look up a team abbreviation from fixture data. */
function getTeamAbbr(teamId: number): string {
  // Check bracket data first (has abbreviation)
  for (const s of bracket) {
    if (s.topSeedTeam?.id === teamId) return s.topSeedTeam.abbreviation ?? '';
    if (s.bottomSeedTeam?.id === teamId)
      return s.bottomSeedTeam.abbreviation ?? '';
  }
  // Fallback: search games
  for (const g of ALL_GAMES) {
    if (g.homeTeam.id === teamId) return g.homeTeam.abbreviation;
    if (g.awayTeam.id === teamId) return g.awayTeam.abbreviation;
  }
  return String(teamId);
}

// ── Determine which round a date falls in ──────────────────────────────
function getRoundForDate(date: string): number {
  // Return the round whose games include this date, or the current active round
  for (let r = 4; r >= 1; r--) {
    const games = ROUND_GAMES[r] ?? [];
    const dates = games.map((g) => g.gameDate).sort();
    if (dates.length > 0 && date >= dates[0]) return r;
  }
  return 1;
}

// ── Public types ───────────────────────────────────────────────────────
export interface MockLiveGame {
  game: NHLGame;
  seriesStatus: SeriesStatus;
}

export interface MockLiveGamesResult {
  games: MockLiveGame[];
  hasGames: boolean;
  message: string; // "No games scheduled today" or game count
}

// ── TanStack Query-shaped result ───────────────────────────────────────
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

// ── Main hook ──────────────────────────────────────────────────────────

/**
 * Mock replacement for live games display.
 * Returns games from fixture data matching the current simulationDate,
 * with series status for each matchup.
 */
export function useMockLiveGames() {
  const { state } = useMockData();
  const { simulationDate, currentRound } = state;

  // Get games for the current simulated date across all rounds up to current
  const todaysGames: MockLiveGame[] = [];

  for (let r = 1; r <= currentRound; r++) {
    const roundGames = ROUND_GAMES[r] ?? [];
    for (const game of roundGames) {
      if (game.gameDate === simulationDate) {
        const seriesStatus = computeSeriesStatus(
          r,
          game.homeTeam.id,
          game.awayTeam.id,
          simulationDate
        );
        todaysGames.push({ game, seriesStatus });
      }
    }
  }

  const hasGames = todaysGames.length > 0;
  const message = hasGames
    ? `${todaysGames.length} game${todaysGames.length > 1 ? 's' : ''} today`
    : 'No games scheduled today';

  const result: MockLiveGamesResult = { games: todaysGames, hasGames, message };
  return makeMockQuery(result);
}

/**
 * Mock replacement for the inline useLiveGames() in DashboardPage.
 * Returns team stats from team_stats_cache shape (non-eliminated teams),
 * filtered by games that have been played through the current simulationDate.
 */
export function useMockLiveGamesTeamStats() {
  const { state } = useMockData();
  const { simulationDate } = state;

  // Gather all teams that have games played through simulationDate
  const teamStats = new Map<
    number,
    {
      team_id: number;
      team_name: string;
      team_abbreviation: string;
      wins: number;
      shutouts: number;
      is_eliminated: boolean;
    }
  >();

  for (const game of ALL_GAMES) {
    if (game.gameDate > simulationDate) continue;

    const homeScore = game.homeTeam.score ?? 0;
    const awayScore = game.awayTeam.score ?? 0;

    // Initialize teams if not seen
    if (!teamStats.has(game.homeTeam.id)) {
      teamStats.set(game.homeTeam.id, {
        team_id: game.homeTeam.id,
        team_name: game.homeTeam.name,
        team_abbreviation: game.homeTeam.abbreviation,
        wins: 0,
        shutouts: 0,
        is_eliminated: false,
      });
    }
    if (!teamStats.has(game.awayTeam.id)) {
      teamStats.set(game.awayTeam.id, {
        team_id: game.awayTeam.id,
        team_name: game.awayTeam.name,
        team_abbreviation: game.awayTeam.abbreviation,
        wins: 0,
        shutouts: 0,
        is_eliminated: false,
      });
    }

    // Count wins and shutouts
    if (homeScore > awayScore) {
      teamStats.get(game.homeTeam.id)!.wins++;
      if (awayScore === 0) teamStats.get(game.homeTeam.id)!.shutouts++;
    } else if (awayScore > homeScore) {
      teamStats.get(game.awayTeam.id)!.wins++;
      if (homeScore === 0) teamStats.get(game.awayTeam.id)!.shutouts++;
    }
  }

  const data = Array.from(teamStats.values()).sort((a, b) => b.wins - a.wins);
  return makeMockQuery(data);
}

/**
 * Mock replacement for getScoresNow() from @sportsnot/nhl-api.
 * Returns NHLGame[] for the given simulated date.
 */
export function mockGetScoresNow(simulationDate: string): NHLGame[] {
  const round = getRoundForDate(simulationDate);
  const games: NHLGame[] = [];
  for (let r = 1; r <= round; r++) {
    for (const g of ROUND_GAMES[r] ?? []) {
      if (g.gameDate === simulationDate) games.push(g);
    }
  }
  return games;
}
