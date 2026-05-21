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
  return IS_MOCK ? mockResult : supabaseResult;
}

export function useCumulativePlayoffPlayersForDraft(
  season: string,
  round: number
) {
  const mockResult = useMockCumulativePlayoffPlayers(season, round);
  const queryResult = useCumulativeDraftStats({
    queryKeyPrefix: 'draft-cumulative-playoff-players',
    cacheTable: 'player_stats_cache',
    season,
    round,
    aggregateRows: aggregatePlayerStats,
  });

  return IS_MOCK ? mockResult : queryResult;
}

export function usePlayoffTeamsForDraft(season: string, round: number) {
  const mockResult = useMockPlayoffTeams(season, round);
  const supabaseResult = useSupabasePlayoffTeams(season, round);
  return IS_MOCK ? mockResult : supabaseResult;
}

export function useCumulativePlayoffTeamsForDraft(
  season: string,
  round: number
) {
  const mockResult = useMockCumulativePlayoffTeams(season, round);
  const queryResult = useCumulativeDraftStats({
    queryKeyPrefix: 'draft-cumulative-playoff-teams',
    cacheTable: 'team_stats_cache',
    season,
    round,
    aggregateRows: aggregateTeamStats,
  });

  return IS_MOCK ? mockResult : queryResult;
}

export function useRegularSeasonPlayersForDraft(season: string) {
  const mockResult = useMockRegularSeasonPlayers(season, true);
  const supabaseResult = useSupabaseRegularSeasonPlayers(season, true);
  return IS_MOCK ? mockResult : supabaseResult;
}

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

interface UseCumulativeDraftStatsParams<TRow, TResult> {
  queryKeyPrefix: string;
  cacheTable: 'player_stats_cache' | 'team_stats_cache';
  season: string;
  round: number;
  aggregateRows: (rows: TRow[]) => TResult[];
}

interface AggregateRowsConfig<TRow, TKey> {
  getKey: (row: TRow) => TKey;
  initialize: (row: TRow) => TRow;
  merge: (existing: TRow, next: TRow) => TRow;
}

function useCumulativeDraftStats<TRow, TResult>(
  params: UseCumulativeDraftStatsParams<TRow, TResult>
) {
  const { queryKeyPrefix, cacheTable, season, round, aggregateRows } = params;
  return useQuery({
    queryKey: [queryKeyPrefix, season, round],
    queryFn: async () => {
      const rows = await fetchCumulativeDraftStats<TRow>({
        cacheTable,
        season,
        round,
      });
      return aggregateRows(rows);
    },
    enabled: !IS_MOCK,
    staleTime: 1000 * 60 * 2,
  });
}

async function fetchCumulativeDraftStats<TRow>(params: {
  cacheTable: 'player_stats_cache' | 'team_stats_cache';
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
