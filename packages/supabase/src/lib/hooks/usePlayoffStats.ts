import { useQuery } from '@tanstack/react-query';
import { supabase } from '../supabase';

/**
 * Fetches cached playoff player stats from Supabase.
 * The sync-nhl-stats edge function populates this data.
 */
export function usePlayoffPlayers(season: string, round: number) {
  return useQuery({
    queryKey: ['playoff-players', season, round],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('player_stats_cache')
        .select('*')
        .eq('nhl_season', season)
        .eq('playoff_round', round)
        .order('goals', { ascending: false });

      if (error) throw error;
      return data ?? [];
    },
    staleTime: 1000 * 60 * 2, // 2 min
  });
}

/**
 * Fetches cached playoff team stats from Supabase.
 */
export function usePlayoffTeams(season: string, round: number) {
  return useQuery({
    queryKey: ['playoff-teams', season, round],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('team_stats_cache')
        .select('*')
        .eq('nhl_season', season)
        .eq('playoff_round', round)
        .order('wins', { ascending: false });

      if (error) throw error;
      return data ?? [];
    },
    staleTime: 1000 * 60 * 2,
  });
}
