import { useQuery } from '@tanstack/react-query';
import { supabase } from '@sportsnot/supabase';
import { useMockCompletedDrafts } from '../../mock/hooks/useMockDraft';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

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
