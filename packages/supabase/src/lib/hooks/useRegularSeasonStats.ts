import { useQuery } from '@tanstack/react-query';
import { supabase } from '../supabase';

/**
 * Fetches regular season player stats from Supabase.
 * Only fetches when `enabled` is true (intended for round 1 only).
 */
export function useRegularSeasonPlayers(
  season: string,
  enabled: boolean
) {
  return useQuery({
    queryKey: ['regular-season-players', season],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('regular_season_stats_cache')
        .select('*')
        .eq('nhl_season', season)
        .order('points', { ascending: false });

      if (error) throw error;
      return data ?? [];
    },
    enabled,
    staleTime: 1000 * 60 * 5, // 5 min — regular season data changes infrequently
  });
}
