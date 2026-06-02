import { useQuery } from '@tanstack/react-query';
import { supabase } from '../supabase';

const PLAYOFF_STATS_STALE_TIME_MS = 1000 * 60 * 2;
type CacheTable = 'player_stats_cache' | 'team_stats_cache';
type CachedScalar = number | string | boolean | null;
type CachedStatsRow = Record<string, CachedScalar>;

interface CachedPlayerStatsRow extends CachedStatsRow {
  player_id: number;
  player_name: string | null;
  position: string | null;
  team_abbreviation: string | null;
  is_injured: boolean | null;
  goals: number | null;
  assists: number | null;
  games_played: number | null;
}

interface CachedTeamStatsRow extends CachedStatsRow {
  team_id: number;
  team_name: string | null;
  team_abbreviation: string | null;
  is_eliminated: boolean | null;
  wins: number | null;
  shutouts: number | null;
}

interface AggregateStatsConfig<
  TRow extends CachedStatsRow,
  TKey extends keyof TRow,
> {
  queryKey: string;
  cacheTable: CacheTable;
  keyField: TKey;
  numericFields: Array<keyof TRow>;
  inheritedFields: Array<keyof TRow>;
}

interface PlayoffStatsConfig {
  queryKey: string;
  cacheTable: CacheTable;
  orderField: string;
}

interface PlayoffStatsFetchConfig {
  cacheTable: CacheTable;
  season: string;
  round: number;
  roundFilter: 'eq' | 'lte';
  orderField: string;
  ascending: boolean;
}

const PLAYER_PLAYOFF_STATS_CONFIG: PlayoffStatsConfig = {
  queryKey: 'playoff-players',
  cacheTable: 'player_stats_cache',
  orderField: 'goals',
};

const TEAM_PLAYOFF_STATS_CONFIG: PlayoffStatsConfig = {
  queryKey: 'playoff-teams',
  cacheTable: 'team_stats_cache',
  orderField: 'wins',
};

const PLAYER_CUMULATIVE_STAT_CONFIG: AggregateStatsConfig<
  CachedPlayerStatsRow,
  'player_id'
> = {
  queryKey: 'cumulative-playoff-players',
  cacheTable: 'player_stats_cache',
  keyField: 'player_id',
  numericFields: ['goals', 'assists', 'games_played'],
  inheritedFields: [
    'player_name',
    'position',
    'team_abbreviation',
    'is_injured',
  ],
};

const TEAM_CUMULATIVE_STAT_CONFIG: AggregateStatsConfig<
  CachedTeamStatsRow,
  'team_id'
> = {
  queryKey: 'cumulative-playoff-teams',
  cacheTable: 'team_stats_cache',
  keyField: 'team_id',
  numericFields: ['wins', 'shutouts'],
  inheritedFields: ['team_name', 'team_abbreviation', 'is_eliminated'],
};

/**
 * Fetches cached playoff player stats from Supabase.
 * The sync-nhl-stats edge function populates this data.
 */
export function usePlayoffPlayers(season: string, round: number) {
  return usePlayoffStatsQuery<CachedPlayerStatsRow>({
    season,
    round,
    statConfig: PLAYER_PLAYOFF_STATS_CONFIG,
  });
}

export function useCumulativePlayoffPlayers(season: string, round: number) {
  return useCumulativePlayoffStats({
    season,
    round,
    statConfig: PLAYER_CUMULATIVE_STAT_CONFIG,
  });
}

/**
 * Fetches cached playoff team stats from Supabase.
 */
export function usePlayoffTeams(season: string, round: number) {
  return usePlayoffStatsQuery<CachedTeamStatsRow>({
    season,
    round,
    statConfig: TEAM_PLAYOFF_STATS_CONFIG,
  });
}

export function useCumulativePlayoffTeams(season: string, round: number) {
  return useCumulativePlayoffStats({
    season,
    round,
    statConfig: TEAM_CUMULATIVE_STAT_CONFIG,
  });
}

function usePlayoffStatsQuery<TRow extends CachedStatsRow>(params: {
  season: string;
  round: number;
  statConfig: PlayoffStatsConfig;
}) {
  const { season, round, statConfig } = params;
  return useQuery({
    queryKey: [statConfig.queryKey, season, round],
    queryFn: async () =>
      fetchPlayoffStatsRows<TRow>({
        cacheTable: statConfig.cacheTable,
        season,
        round,
        roundFilter: 'eq',
        orderField: statConfig.orderField,
        ascending: false,
      }),
    staleTime: PLAYOFF_STATS_STALE_TIME_MS,
  });
}

function useCumulativePlayoffStats<
  TRow extends CachedStatsRow,
  TKey extends keyof TRow,
>(params: {
  season: string;
  round: number;
  statConfig: AggregateStatsConfig<TRow, TKey>;
}) {
  const { season, round, statConfig } = params;
  return useQuery({
    queryKey: [statConfig.queryKey, season, round],
    queryFn: async () => {
      const rows = await fetchPlayoffStatsRows<TRow>({
        cacheTable: statConfig.cacheTable,
        season,
        round,
        roundFilter: 'lte',
        orderField: 'playoff_round',
        ascending: true,
      });
      return aggregateCumulativeRows(rows, statConfig);
    },
    staleTime: PLAYOFF_STATS_STALE_TIME_MS,
  });
}

async function fetchPlayoffStatsRows<TRow extends CachedStatsRow>(
  params: PlayoffStatsFetchConfig
) {
  const { ascending, cacheTable, orderField, round, roundFilter, season } =
    params;
  const roundQuery = supabase
    .from(cacheTable)
    .select('*')
    .eq('nhl_season', season);
  const scopedQuery =
    roundFilter === 'eq'
      ? roundQuery.eq('playoff_round', round)
      : roundQuery.lte('playoff_round', round);
  const { data, error } = await scopedQuery.order(orderField, { ascending });

  if (error) throw error;
  return (data ?? []) as TRow[];
}

function aggregateCumulativeRows<
  TRow extends CachedStatsRow,
  TKey extends keyof TRow,
>(rows: TRow[], config: AggregateStatsConfig<TRow, TKey>) {
  const rowsById = new Map<TRow[TKey], TRow>();

  for (const row of rows) {
    const key = row[config.keyField];
    const existing = rowsById.get(key);
    rowsById.set(
      key,
      existing
        ? mergeCumulativeRow(existing, row, config)
        : initializeCumulativeRow(row, config)
    );
  }

  return [...rowsById.values()];
}

function initializeCumulativeRow<
  TRow extends CachedStatsRow,
  TKey extends keyof TRow,
>(row: TRow, config: AggregateStatsConfig<TRow, TKey>) {
  const initialized = { ...row };
  for (const field of config.numericFields) {
    initialized[field] = normalizeNumericValue(
      row[field]
    ) as TRow[typeof field];
  }
  return initialized;
}

function mergeCumulativeRow<
  TRow extends CachedStatsRow,
  TKey extends keyof TRow,
>(existing: TRow, next: TRow, config: AggregateStatsConfig<TRow, TKey>) {
  const merged = { ...existing };
  for (const field of config.inheritedFields) {
    merged[field] = (next[field] ?? existing[field]) as TRow[typeof field];
  }
  for (const field of config.numericFields) {
    merged[field] = (normalizeNumericValue(existing[field]) +
      normalizeNumericValue(next[field])) as TRow[typeof field];
  }
  return merged;
}

function normalizeNumericValue(value: CachedScalar) {
  return typeof value === 'number' ? value : 0;
}
