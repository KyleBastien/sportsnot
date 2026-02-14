import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '../supabase';

export function useLeagues(userId: string | undefined) {
  return useQuery({
    queryKey: ['leagues', userId],
    queryFn: async () => {
      if (!userId) return [];
      const { data, error } = await supabase
        .from('league_members')
        .select(
          'id, team_name, total_points, leagues(id, name, status, current_round, max_participants, commissioner_id, invite_code)'
        )
        .eq('user_id', userId);

      if (error) throw error;
      return data ?? [];
    },
    enabled: !!userId,
  });
}

export function useLeague(leagueId: string | undefined) {
  return useQuery({
    queryKey: ['league', leagueId],
    queryFn: async () => {
      if (!leagueId) return null;
      const { data, error } = await supabase
        .from('leagues')
        .select(
          '*, league_members(id, user_id, team_name, total_points, users(display_name, avatar_url))'
        )
        .eq('id', leagueId)
        .single();

      if (error) throw error;
      return data;
    },
    enabled: !!leagueId,
  });
}

export function useCreateLeague() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: {
      name: string;
      maxParticipants: number;
      inviteCode: string;
      commissionerId: string;
    }) => {
      const { data: league, error: leagueError } = await supabase
        .from('leagues')
        .insert({
          name: params.name,
          max_participants: params.maxParticipants,
          invite_code: params.inviteCode,
          commissioner_id: params.commissionerId,
        })
        .select()
        .single();

      if (leagueError) throw leagueError;

      // Auto-join commissioner
      const { error: memberError } = await supabase
        .from('league_members')
        .insert({
          league_id: league.id,
          user_id: params.commissionerId,
          team_name: `Team ${params.name}`,
        });

      if (memberError) throw memberError;
      return league;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['leagues'] });
    },
  });
}

export function useJoinLeague() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: {
      inviteCode: string;
      userId: string;
      teamName: string;
    }) => {
      // Find league by invite code
      const { data: league, error: findError } = await supabase
        .from('leagues')
        .select('id, name, max_participants')
        .eq('invite_code', params.inviteCode)
        .single();

      if (findError) throw new Error('Invalid invite code');

      // Check member count
      const { count } = await supabase
        .from('league_members')
        .select('id', { count: 'exact', head: true })
        .eq('league_id', league.id);

      if (count !== null && count >= league.max_participants) {
        throw new Error('League is full');
      }

      // Join league
      const { error: joinError } = await supabase
        .from('league_members')
        .insert({
          league_id: league.id,
          user_id: params.userId,
          team_name: params.teamName,
        });

      if (joinError) {
        if (joinError.code === '23505') {
          throw new Error('You already belong to this league');
        }
        throw joinError;
      }

      return league;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['leagues'] });
    },
  });
}
