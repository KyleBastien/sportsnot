import type { NHLPlayoffSeries, NHLGame } from '@sportsnot/types';
import {
  bracket,
  gamesR1,
  gamesR2,
  gamesCf,
  gamesScf,
} from '@sportsnot/mock-data';
import { useMockData } from '../MockDataProvider';

// ── All fixture games by round ─────────────────────────────────────────
const ROUND_GAMES: Record<number, NHLGame[]> = {
  1: gamesR1 as unknown as NHLGame[],
  2: gamesR2 as unknown as NHLGame[],
  3: gamesCf as unknown as NHLGame[],
  4: gamesScf as unknown as NHLGame[],
};

// ── Series win counter ─────────────────────────────────────────────────

/** Make a deterministic key for a matchup (sorted team IDs). */
function seriesKey(teamA: number, teamB: number): string {
  return [teamA, teamB].sort((a, b) => a - b).join('-');
}

interface WinCounts {
  topSeedWins: number;
  bottomSeedWins: number;
}

/**
 * Count wins for a series' top/bottom seed teams based on games
 * played through `throughDate` in the given round.
 */
function countSeriesWins(
  round: number,
  topSeedId: number,
  bottomSeedId: number,
  throughDate: string,
): WinCounts {
  const games = ROUND_GAMES[round] ?? [];
  const key = seriesKey(topSeedId, bottomSeedId);

  let topSeedWins = 0;
  let bottomSeedWins = 0;

  for (const g of games) {
    if (g.gameDate > throughDate) continue;
    if (seriesKey(g.homeTeam.id, g.awayTeam.id) !== key) continue;

    const homeScore = g.homeTeam.score ?? 0;
    const awayScore = g.awayTeam.score ?? 0;
    if (homeScore === awayScore) continue;

    const winnerId = homeScore > awayScore ? g.homeTeam.id : g.awayTeam.id;
    if (winnerId === topSeedId) topSeedWins++;
    else bottomSeedWins++;
  }

  return { topSeedWins, bottomSeedWins };
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

// ── Derive bracket state from simulation progress ──────────────────────

/**
 * Build the live bracket by starting from the fixture bracket.ts
 * (which has all 16 teams in their seeding positions) and overlaying
 * win counts / series completion derived from game fixtures through
 * the current simulated date.
 */
function deriveBracketState(
  simulationDate: string,
  currentRound: number,
): NHLPlayoffSeries[] {
  const baseBracket = bracket as unknown as NHLPlayoffSeries[];

  return baseBracket.map((series) => {
    const topId = series.topSeedTeam?.id;
    const bottomId = series.bottomSeedTeam?.id;

    // If we haven't reached this round yet, show teams but no results
    if (series.round > currentRound) {
      return {
        ...series,
        topSeedWins: 0,
        bottomSeedWins: 0,
        matchupTeams: series.matchupTeams
          ? {
              topSeed: {
                ...series.matchupTeams.topSeed,
                seriesRecord: { wins: 0, losses: 0 },
              },
              bottomSeed: {
                ...series.matchupTeams.bottomSeed,
                seriesRecord: { wins: 0, losses: 0 },
              },
            }
          : undefined,
        isComplete: false,
        seriesWinner: undefined,
      };
    }

    // If teams are unknown for this series, return as-is
    if (topId == null || bottomId == null) {
      return { ...series, isComplete: false, seriesWinner: undefined };
    }

    // Count wins from fixture games through simulation date
    const { topSeedWins, bottomSeedWins } = countSeriesWins(
      series.round,
      topId,
      bottomId,
      simulationDate,
    );

    const isComplete = topSeedWins >= 4 || bottomSeedWins >= 4;

    let seriesWinner: NHLPlayoffSeries['seriesWinner'];
    if (isComplete) {
      if (topSeedWins >= 4 && series.topSeedTeam) {
        seriesWinner = { id: series.topSeedTeam.id, name: series.topSeedTeam.name };
      } else if (bottomSeedWins >= 4 && series.bottomSeedTeam) {
        seriesWinner = { id: series.bottomSeedTeam.id, name: series.bottomSeedTeam.name };
      }
    }

    return {
      ...series,
      topSeedWins,
      bottomSeedWins,
      matchupTeams: series.matchupTeams
        ? {
            topSeed: {
              ...series.matchupTeams.topSeed,
              seriesRecord: { wins: topSeedWins, losses: bottomSeedWins },
            },
            bottomSeed: {
              ...series.matchupTeams.bottomSeed,
              seriesRecord: { wins: bottomSeedWins, losses: topSeedWins },
            },
          }
        : undefined,
      isComplete,
      seriesWinner,
    };
  });
}

// ── Public hooks ───────────────────────────────────────────────────────

/**
 * Mock replacement for usePlayoffBracket / getPlayoffBracket.
 * Derives bracket state from simulation progress:
 * - Before simulation: all 16 teams in correct seeding positions
 * - During simulation: series scores updated from game results through simulationDate
 * - After a round: series winners shown, losers eliminated
 * - After round 4: Stanley Cup champion displayed
 */
export function useMockPlayoffBracket() {
  const { state } = useMockData();
  const { simulationDate, currentRound, seasonComplete } = state;

  const bracketData = deriveBracketState(simulationDate, currentRound);

  // Find the Stanley Cup champion (round 4 series winner) if season is complete
  let champion: { id: number; name: string } | null = null;
  if (seasonComplete) {
    const finalSeries = bracketData.find((s) => s.round === 4 && s.isComplete);
    if (finalSeries?.seriesWinner) {
      champion = finalSeries.seriesWinner;
    }
  }

  return makeMockQuery({ bracket: bracketData, champion });
}

/**
 * Async function replacement for getPlayoffBracket().
 * Returns NHLPlayoffSeries[] with wins computed through the given date.
 */
export async function mockGetPlayoffBracketForDate(
  simulationDate: string,
  currentRound: number,
): Promise<NHLPlayoffSeries[]> {
  return deriveBracketState(simulationDate, currentRound);
}
