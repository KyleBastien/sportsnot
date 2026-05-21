import { useQuery } from '@tanstack/react-query';
import {
  supabase,
  usePlayoffPlayers as useSupabasePlayoffPlayers,
  usePlayoffTeams as useSupabasePlayoffTeams,
  useRegularSeasonPlayers as useSupabaseRegularSeasonPlayers,
} from '@sportsnot/supabase';
import {
  useMockDraft,
  useMockLeagueMembers,
} from '../../../mock/hooks/useMockDraft';
import {
  useMockCumulativePlayoffPlayers,
  useMockCumulativePlayoffTeams,
  useMockPlayoffPlayers,
  useMockPlayoffTeams,
  useMockRegularSeasonPlayers,
} from '../../../mock/hooks/useMockNhlApi';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';
const CUMULATIVE_STATS_STALE_TIME_MS = 1000 * 60 * 2;

export function useDraft(leagueId: string) {
  const mockResult = useMockDraft(leagueId);

  const queryResult = useQuery({
    queryKey: ['draft', leagueId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('drafts')
        .select('*, draft_picks(*, league_members(team_name, user_id))')
        .eq('league_id', leagueId)
        .order('round', { ascending: false })
        .limit(1)
        .single();

      if (error) throw error;
      return data;
    },
    enabled: !IS_MOCK,
    refetchInterval: IS_MOCK ? false : 3000,
  });

  return IS_MOCK ? mockResult : queryResult;
}

export function useLeagueMembers(leagueId: string) {
  const mockResult = useMockLeagueMembers(leagueId);

  const queryResult = useQuery({
    queryKey: ['league-members', leagueId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('league_members')
        .select('id, user_id, team_name, total_points, users(display_name)')
        .eq('league_id', leagueId);

      if (error) throw error;
      return data ?? [];
    },
    enabled: !IS_MOCK,
  });

  return IS_MOCK ? mockResult : queryResult;
}

export function useLeagueInfo(leagueId: string) {
  return useQuery({
    queryKey: ['league-info', leagueId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('leagues')
        .select('commissioner_id, allow_ir_slots')
        .eq('id', leagueId)
        .single();

      if (error) throw error;
      return {
        commissionerId: data?.commissioner_id as string | null,
        allowIrSlots: (data?.allow_ir_slots ?? true) as boolean,
      };
    },
    enabled: !IS_MOCK,
  });
}

export function usePlayoffPlayersForDraft(season: string, round: number) {
  const mockResult = useMockPlayoffPlayers(season, round);
  const supabaseResult = useSupabasePlayoffPlayers(season, round);
  return selectDraftQuerySource(mockResult, supabaseResult);
}

export function useCumulativePlayoffPlayersForDraft(
  season: string,
  round: number
) {
  const mockResult = useMockCumulativePlayoffPlayers(season, round);
  const queryResult = useCumulativeDraftStats({
    season,
    round,
    mockResult,
    statConfig: PLAYER_CUMULATIVE_STAT_CONFIG,
  });
  return selectDraftQuerySource(mockResult, queryResult);
}

export function usePlayoffTeamsForDraft(season: string, round: number) {
  const mockResult = useMockPlayoffTeams(season, round);
  const supabaseResult = useSupabasePlayoffTeams(season, round);
  return selectDraftQuerySource(mockResult, supabaseResult);
}

export function useCumulativePlayoffTeamsForDraft(
  season: string,
  round: number
) {
  const mockResult = useMockCumulativePlayoffTeams(season, round);
  const queryResult = useCumulativeDraftStats({
    season,
    round,
    mockResult,
    statConfig: TEAM_CUMULATIVE_STAT_CONFIG,
  });
  return selectDraftQuerySource(mockResult, queryResult);
}

export function useRegularSeasonPlayersForDraft(season: string) {
  const mockResult = useMockRegularSeasonPlayers(season, true);
  const supabaseResult = useSupabaseRegularSeasonPlayers(season, true);
  return selectDraftQuerySource(mockResult, supabaseResult);
}

function selectDraftQuerySource<T>(mockResult: T, queryResult: T) {
  return IS_MOCK ? mockResult : queryResult;
}

type CacheTable = 'player_stats_cache' | 'team_stats_cache';
type CachedScalar = number | string | boolean | null;
type CachedStatsRow = Record<string, CachedScalar>;

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

const PLAYER_CUMULATIVE_STAT_CONFIG: AggregateStatsConfig<
  CachedPlayerStatsRow,
  'player_id'
> = {
  queryKey: 'draft-cumulative-playoff-players',
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
  queryKey: 'draft-cumulative-playoff-teams',
  cacheTable: 'team_stats_cache',
  keyField: 'team_id',
  numericFields: ['wins', 'shutouts'],
  inheritedFields: ['team_name', 'team_abbreviation', 'is_eliminated'],
};

function useCumulativeDraftStats<
  TRow extends CachedStatsRow,
  TKey extends keyof TRow,
  TMockResult,
>(params: {
  season: string;
  round: number;
  mockResult: TMockResult;
  statConfig: AggregateStatsConfig<TRow, TKey>;
}) {
  const { season, round, statConfig } = params;
  return useQuery({
    queryKey: [statConfig.queryKey, season, round],
    queryFn: async () => {
      const rows = await fetchCumulativeDraftStats<TRow>({
        cacheTable: statConfig.cacheTable,
        season,
        round,
      });
      return aggregateCumulativeRows(rows, statConfig);
    },
    enabled: !IS_MOCK,
    staleTime: CUMULATIVE_STATS_STALE_TIME_MS,
  });
}

async function fetchCumulativeDraftStats<TRow>(params: {
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
