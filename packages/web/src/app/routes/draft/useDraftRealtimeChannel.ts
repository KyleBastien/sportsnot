import { useEffect } from 'react';
import { supabase } from '@sportsnot/supabase';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

export function useDraftRealtimeChannel(leagueId: string) {
  useEffect(() => {
    if (IS_MOCK) {
      return;
    }

    const channel = supabase
      .channel(`draft-${leagueId}`)
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'draft_picks' },
        () => undefined
      )
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'drafts' },
        () => undefined
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [leagueId]);
}
