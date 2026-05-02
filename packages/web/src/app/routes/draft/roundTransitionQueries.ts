import { useQuery } from '@tanstack/react-query';
import { supabase } from '@sportsnot/supabase';
import { useMockLeague } from '../../../mock/hooks/useMockLeagues';
import { useMockCompletedDrafts } from '../../../mock/hooks/useMockDraft';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

export function useTransitionLeague(leagueId: string | undefined) {
  const mockResult = useMockLeague(leagueId);

  const queryResult = useQuery({
    queryKey: ['round-transition', leagueId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('leagues')
        .select(
          '*, league_members(id, user_id, team_name, total_points, users(display_name))'
        )
        .eq('id', leagueId!)
        .single();

      if (error) throw error;
      return data;
    },
    enabled: !IS_MOCK && !!leagueId,
  });

  return IS_MOCK ? mockResult : queryResult;
}

export function useCompletedDrafts(leagueId: string | undefined) {
  const mockResult = useMockCompletedDrafts(leagueId);

  const queryResult = useQuery({
    queryKey: ['completed-drafts', leagueId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('drafts')
        .select('id, round, status, completed_at')
        .eq('league_id', leagueId!)
        .eq('status', 'completed')
        .order('round', { ascending: true });

      if (error) throw error;
      return data ?? [];
    },
    enabled: !IS_MOCK && !!leagueId,
  });

  return IS_MOCK ? mockResult : queryResult;
}
