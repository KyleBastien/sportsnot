import { useQuery } from '@tanstack/react-query';
import { supabase } from '@sportsnot/supabase';
import { useMockLeague } from '../../../mock/hooks/useMockLeagues';
import { useMockDraft } from '../../../mock/hooks/useMockDraft';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

export function useLeagueForLobby(leagueId: string) {
  const mockResult = useMockLeague(leagueId);

  const queryResult = useQuery({
    queryKey: ['draft-lobby', leagueId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('leagues')
        .select(
          '*, league_members(id, user_id, team_name, users(display_name))'
        )
        .eq('id', leagueId)
        .single();

      if (error) throw error;
      return data;
    },
    enabled: !IS_MOCK && !!leagueId,
    refetchInterval: IS_MOCK ? false : 5000,
  });

  return IS_MOCK ? mockResult : queryResult;
}

export function useActiveDraftCheck(leagueId: string) {
  const mockDraftResult = useMockDraft(leagueId);

  const queryResult = useQuery({
    queryKey: ['active-draft-check', leagueId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('drafts')
        .select('id, status')
        .eq('league_id', leagueId)
        .eq('status', 'active')
        .maybeSingle();

      if (error) throw error;
      return data;
    },
    enabled: !IS_MOCK && !!leagueId,
    refetchInterval: IS_MOCK ? false : 3000,
  });

  if (IS_MOCK) {
    return {
      ...mockDraftResult,
      data:
        mockDraftResult.data?.status === 'active' ? mockDraftResult.data : null,
    };
  }

  return queryResult;
}
