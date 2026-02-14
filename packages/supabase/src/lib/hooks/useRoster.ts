import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '../supabase';

export function useRoster(leagueMemberId: string | undefined, round: number) {
  return useQuery({
    queryKey: ['roster', leagueMemberId, round],
    queryFn: async () => {
      if (!leagueMemberId) return [];
      const { data, error } = await supabase
        .from('rosters')
        .select('*')
        .eq('league_member_id', leagueMemberId)
        .eq('round', round);

      if (error) throw error;
      return data ?? [];
    },
    enabled: !!leagueMemberId,
  });
}

export function useLeagueRosters(leagueId: string | undefined, round: number) {
  return useQuery({
    queryKey: ['league-rosters', leagueId, round],
    queryFn: async () => {
      if (!leagueId) return [];
      const { data, error } = await supabase
        .from('rosters')
        .select('*, league_members(user_id, team_name)')
        .eq('round', round)
        .in(
          'league_member_id',
          (
            await supabase
              .from('league_members')
              .select('id')
              .eq('league_id', leagueId)
          ).data?.map((m) => m.id) ?? []
        );

      if (error) throw error;
      return data ?? [];
    },
    enabled: !!leagueId,
  });
}

export function useActivateIR() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: {
      leagueMemberId: string;
      round: number;
      injuredSlotId: string;
      irSlotId: string;
    }) => {
      // Call the database function for retroactive IR activation
      const { error } = await supabase.rpc('activate_ir_player', {
        p_league_member_id: params.leagueMemberId,
        p_round: params.round,
        p_injured_roster_id: params.injuredSlotId,
        p_ir_roster_id: params.irSlotId,
      });

      if (error) throw error;
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ['roster', variables.leagueMemberId, variables.round],
      });
    },
  });
}
