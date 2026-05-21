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
  const queryResult = useQuery({
    queryKey: ['draft-cumulative-playoff-players', season, round],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('player_stats_cache')
        .select('*')
        .eq('nhl_season', season)
        .lte('playoff_round', round)
        .order('playoff_round', { ascending: true });

      if (error) throw error;
      return aggregatePlayerStats(data ?? []);
    },
    enabled: !IS_MOCK,
    staleTime: 1000 * 60 * 2,
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
  const queryResult = useQuery({
    queryKey: ['draft-cumulative-playoff-teams', season, round],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('team_stats_cache')
        .select('*')
        .eq('nhl_season', season)
        .lte('playoff_round', round)
        .order('playoff_round', { ascending: true });

      if (error) throw error;
      return aggregateTeamStats(data ?? []);
    },
    enabled: !IS_MOCK,
    staleTime: 1000 * 60 * 2,
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

function aggregatePlayerStats(rows: CachedPlayerStatsRow[]) {
  const rowsByPlayerId = new Map<number, CachedPlayerStatsRow>();

  for (const row of rows) {
    const existing = rowsByPlayerId.get(row.player_id);
    if (!existing) {
      rowsByPlayerId.set(row.player_id, {
        ...row,
        goals: row.goals ?? 0,
        assists: row.assists ?? 0,
        games_played: row.games_played ?? 0,
      });
      continue;
    }

    rowsByPlayerId.set(row.player_id, {
      ...existing,
      player_name: row.player_name ?? existing.player_name,
      position: row.position ?? existing.position,
      team_abbreviation: row.team_abbreviation ?? existing.team_abbreviation,
      is_injured: row.is_injured ?? existing.is_injured,
      goals: (existing.goals ?? 0) + (row.goals ?? 0),
      assists: (existing.assists ?? 0) + (row.assists ?? 0),
      games_played: (existing.games_played ?? 0) + (row.games_played ?? 0),
    });
  }

  return [...rowsByPlayerId.values()];
}

function aggregateTeamStats(rows: CachedTeamStatsRow[]) {
  const rowsByTeamId = new Map<number, CachedTeamStatsRow>();

  for (const row of rows) {
    const existing = rowsByTeamId.get(row.team_id);
    if (!existing) {
      rowsByTeamId.set(row.team_id, {
        ...row,
        wins: row.wins ?? 0,
        shutouts: row.shutouts ?? 0,
      });
      continue;
    }

    rowsByTeamId.set(row.team_id, {
      ...existing,
      team_name: row.team_name ?? existing.team_name,
      team_abbreviation: row.team_abbreviation ?? existing.team_abbreviation,
      is_eliminated: row.is_eliminated ?? existing.is_eliminated,
      wins: (existing.wins ?? 0) + (row.wins ?? 0),
      shutouts: (existing.shutouts ?? 0) + (row.shutouts ?? 0),
    });
  }

  return [...rowsByTeamId.values()];
}
