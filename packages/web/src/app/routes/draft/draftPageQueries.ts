import { useQuery } from '@tanstack/react-query';
import {
  supabase,
  useCumulativePlayoffPlayers as useSupabaseCumulativePlayoffPlayers,
  useCumulativePlayoffTeams as useSupabaseCumulativePlayoffTeams,
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

interface LeagueQueryParams {
  leagueId: string;
}

interface DraftStatQueryParams {
  season: string;
  round: number;
}

interface SeasonQueryParams {
  season: string;
}

export function useDraft(params: LeagueQueryParams) {
  const { leagueId } = params;
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

export function useLeagueMembers(params: LeagueQueryParams) {
  const { leagueId } = params;
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

export function useLeagueInfo(params: LeagueQueryParams) {
  const { leagueId } = params;
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

export function usePlayoffPlayersForDraft(params: DraftStatQueryParams) {
  const { season, round } = params;
  const mockResult = useMockPlayoffPlayers(season, round);
  const supabaseResult = useSupabasePlayoffPlayers(season, round);
  return selectDraftQuerySource(mockResult, supabaseResult);
}

export function useCumulativePlayoffPlayersForDraft(
  params: DraftStatQueryParams
) {
  const { season, round } = params;
  const mockResult = useMockCumulativePlayoffPlayers(season, round);
  const queryResult = useSupabaseCumulativePlayoffPlayers(season, round);
  return selectDraftQuerySource(mockResult, queryResult);
}

export function usePlayoffTeamsForDraft(params: DraftStatQueryParams) {
  const { season, round } = params;
  const mockResult = useMockPlayoffTeams(season, round);
  const supabaseResult = useSupabasePlayoffTeams(season, round);
  return selectDraftQuerySource(mockResult, supabaseResult);
}

export function useCumulativePlayoffTeamsForDraft(
  params: DraftStatQueryParams
) {
  const { season, round } = params;
  const mockResult = useMockCumulativePlayoffTeams(season, round);
  const queryResult = useSupabaseCumulativePlayoffTeams(season, round);
  return selectDraftQuerySource(mockResult, queryResult);
}

export function useRegularSeasonPlayersForDraft(params: SeasonQueryParams) {
  const { season } = params;
  const mockResult = useMockRegularSeasonPlayers(season, true);
  const supabaseResult = useSupabaseRegularSeasonPlayers(season, true);
  return selectDraftQuerySource(mockResult, supabaseResult);
}

function selectDraftQuerySource<T>(mockResult: T, queryResult: T) {
  return IS_MOCK ? mockResult : queryResult;
}
