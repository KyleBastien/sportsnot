import { useQuery } from '@tanstack/react-query';
import { supabase } from '../supabase';

export interface ScoringEventsFilters {
  memberId?: string;
  eventType?: 'goal' | 'assist' | 'win' | 'shutout';
  dateFrom?: string;
  dateTo?: string;
  playerId?: number;
  teamId?: number;
}

const PAGE_SIZE = 20;

export function useScoringEvents(
  leagueId: string | undefined,
  filters?: ScoringEventsFilters,
  page = 0
) {
  return useQuery({
    queryKey: ['scoringEvents', leagueId, filters, page],
    queryFn: async () => {
      if (!leagueId) return { data: [], count: 0 };

      let query = supabase
        .from('scoring_events')
        .select('*', { count: 'exact' })
        .eq('league_id', leagueId)
        .order('created_at', { ascending: false })
        .range(page * PAGE_SIZE, (page + 1) * PAGE_SIZE - 1);

      if (filters?.memberId) {
        query = query.eq('member_id', filters.memberId);
      }
      if (filters?.eventType) {
        query = query.eq('event_type', filters.eventType);
      }
      if (filters?.dateFrom) {
        query = query.gte('game_date', filters.dateFrom);
      }
      if (filters?.dateTo) {
        query = query.lte('game_date', filters.dateTo);
      }
      if (filters?.playerId) {
        query = query.eq('player_id', filters.playerId);
      }
      if (filters?.teamId) {
        query = query.eq('team_id', filters.teamId);
      }

      const { data, error, count } = await query;

      if (error) throw error;
      return { data: data ?? [], count: count ?? 0 };
    },
    enabled: !!leagueId,
  });
}
