import { useQuery } from '@tanstack/react-query';
import { supabase } from '@sportsnot/supabase';
import { useMockLeague } from '../../../mock/hooks/useMockLeagues';

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
