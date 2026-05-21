import { useQuery } from '@tanstack/react-query';
import { supabase } from '@sportsnot/supabase';
import {
  useMockCumulativePlayoffPlayers,
  useMockCumulativePlayoffTeams,
} from '../../../mock/hooks/useMockNhlApi';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';
const CUMULATIVE_STATS_STALE_TIME_MS = 1000 * 60 * 2;

type CacheTable = 'player_stats_cache' | 'team_stats_cache';

interface CachedPlayerStatsRow {
  player_id: number;
  player_name: string | null;
  position: string | null;
  team_abbreviation: string | null;
  is_injured: boolean | null;
  goals: number | null;
  assists: number | null;
  games_played: number | null;
}

interface CachedTeamStatsRow {
  team_id: number;
  team_name: string | null;
  team_abbreviation: string | null;
  is_eliminated: boolean | null;
  wins: number | null;
  shutouts: number | null;
}

interface CumulativeQueryConfig<TRow, TResult> {
  queryKey: string;
  cacheTable: CacheTable;
  season: string;
  round: number;
  aggregateRows: (rows: TRow[]) => TResult[];
}

interface AggregateRowsConfig<TRow, TKey> {
  getKey: (row: TRow) => TKey;
  initialize: (row: TRow) => TRow;
  merge: (existing: TRow, next: TRow) => TRow;
}

export function useCumulativePlayoffPlayersForDraft(
  season: string,
  round: number
) {
  const mockResult = useMockCumulativePlayoffPlayers(season, round);
  const queryResult = useCumulativeDraftStatQuery({
    queryKey: 'draft-cumulative-playoff-players',
    cacheTable: 'player_stats_cache',
    season,
    round,
    aggregateRows: aggregatePlayerStats,
  });

  return selectDraftStatSource(mockResult, queryResult);
}

export function useCumulativePlayoffTeamsForDraft(
  season: string,
  round: number
) {
  const mockResult = useMockCumulativePlayoffTeams(season, round);
  const queryResult = useCumulativeDraftStatQuery({
    queryKey: 'draft-cumulative-playoff-teams',
    cacheTable: 'team_stats_cache',
    season,
    round,
    aggregateRows: aggregateTeamStats,
  });

  return selectDraftStatSource(mockResult, queryResult);
}

function selectDraftStatSource<T>(mockResult: T, queryResult: T) {
  return IS_MOCK ? mockResult : queryResult;
}

function useCumulativeDraftStatQuery<TRow, TResult>(
  config: CumulativeQueryConfig<TRow, TResult>
) {
  const { queryKey, cacheTable, season, round, aggregateRows } = config;
  return useQuery({
    queryKey: [queryKey, season, round],
    queryFn: async () => {
      const rows = await fetchCumulativeDraftStatRows<TRow>({
        cacheTable,
        season,
        round,
      });
      return aggregateRows(rows);
    },
    enabled: !IS_MOCK,
    staleTime: CUMULATIVE_STATS_STALE_TIME_MS,
  });
}

async function fetchCumulativeDraftStatRows<TRow>(params: {
  cacheTable: CacheTable;
  season: string;
  round: number;
}) {
  const { cacheTable, season, round } = params;
  const { data, error } = await supabase
    .from(cacheTable)
    .select('*')
    .eq('nhl_season', season)
    .lte('playoff_round', round)
    .order('playoff_round', { ascending: true });

  if (error) throw error;
  return (data ?? []) as TRow[];
}

function aggregatePlayerStats(rows: CachedPlayerStatsRow[]) {
  return aggregateRows(rows, {
    getKey: (row) => row.player_id,
    initialize: initializePlayerStatsRow,
    merge: mergePlayerStatsRow,
  });
}

function aggregateTeamStats(rows: CachedTeamStatsRow[]) {
  return aggregateRows(rows, {
    getKey: (row) => row.team_id,
    initialize: initializeTeamStatsRow,
    merge: mergeTeamStatsRow,
  });
}

function aggregateRows<TRow, TKey>(
  rows: TRow[],
  config: AggregateRowsConfig<TRow, TKey>
) {
  const rowsById = new Map<TKey, TRow>();

  for (const row of rows) {
    const key = config.getKey(row);
    const existing = rowsById.get(key);
    rowsById.set(
      key,
      existing ? config.merge(existing, row) : config.initialize(row)
    );
  }

  return [...rowsById.values()];
}

function initializePlayerStatsRow(
  row: CachedPlayerStatsRow
): CachedPlayerStatsRow {
  return {
    ...row,
    goals: row.goals ?? 0,
    assists: row.assists ?? 0,
    games_played: row.games_played ?? 0,
  };
}

function mergePlayerStatsRow(
  existing: CachedPlayerStatsRow,
  next: CachedPlayerStatsRow
): CachedPlayerStatsRow {
  return {
    ...existing,
    player_name: next.player_name ?? existing.player_name,
    position: next.position ?? existing.position,
    team_abbreviation: next.team_abbreviation ?? existing.team_abbreviation,
    is_injured: next.is_injured ?? existing.is_injured,
    goals: (existing.goals ?? 0) + (next.goals ?? 0),
    assists: (existing.assists ?? 0) + (next.assists ?? 0),
    games_played: (existing.games_played ?? 0) + (next.games_played ?? 0),
  };
}

function initializeTeamStatsRow(row: CachedTeamStatsRow): CachedTeamStatsRow {
  return {
    ...row,
    wins: row.wins ?? 0,
    shutouts: row.shutouts ?? 0,
  };
}

function mergeTeamStatsRow(
  existing: CachedTeamStatsRow,
  next: CachedTeamStatsRow
): CachedTeamStatsRow {
  return {
    ...existing,
    team_name: next.team_name ?? existing.team_name,
    team_abbreviation: next.team_abbreviation ?? existing.team_abbreviation,
    is_eliminated: next.is_eliminated ?? existing.is_eliminated,
    wins: (existing.wins ?? 0) + (next.wins ?? 0),
    shutouts: (existing.shutouts ?? 0) + (next.shutouts ?? 0),
  };
}
