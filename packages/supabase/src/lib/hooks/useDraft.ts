import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { supabase } from '../supabase';

export function useDraft(leagueId: string | undefined) {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ['draft', leagueId],
    queryFn: async () => {
      if (!leagueId) return null;
      const { data, error } = await supabase
        .from('drafts')
        .select('*, draft_picks(*, league_members(team_name, user_id))')
        .eq('league_id', leagueId)
        .order('round', { ascending: false })
        .limit(1)
        .single();

      if (error && error.code !== 'PGRST116') throw error;
      return data;
    },
    enabled: !!leagueId,
    refetchInterval: 5000,
  });

  // Real-time subscription for draft changes
  useEffect(() => {
    if (!leagueId) return;

    const channel = supabase
      .channel(`draft-${leagueId}`)
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'drafts', filter: `league_id=eq.${leagueId}` },
        () => queryClient.invalidateQueries({ queryKey: ['draft', leagueId] })
      )
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'draft_picks' },
        () => queryClient.invalidateQueries({ queryKey: ['draft', leagueId] })
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [leagueId, queryClient]);

  return query;
}

export function useMakePick() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: {
      draftId: string;
      leagueMemberId: string;
      pickNumber: number;
      playerId: number | null;
      teamId: number | null;
      position: string;
    }) => {
      const { error: pickError } = await supabase.from('draft_picks').insert({
        draft_id: params.draftId,
        league_member_id: params.leagueMemberId,
        pick_number: params.pickNumber,
        player_id: params.playerId,
        team_id: params.teamId,
        position: params.position,
      });

      if (pickError) throw pickError;

      // Advance current pick
      const { error: advanceError } = await supabase
        .from('drafts')
        .update({ current_pick: params.pickNumber + 1 })
        .eq('id', params.draftId);

      if (advanceError) throw advanceError;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['draft'] });
    },
  });
}

export function useStartDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: {
      leagueId: string;
      round: number;
      draftOrder: string[];
    }) => {
      const { data, error } = await supabase
        .from('drafts')
        .insert({
          league_id: params.leagueId,
          round: params.round,
          status: 'active',
          current_pick: 1,
          draft_order: params.draftOrder,
          started_at: new Date().toISOString(),
        })
        .select()
        .single();

      if (error) throw error;

      // Update league status
      await supabase
        .from('leagues')
        .update({ status: 'drafting', current_round: params.round })
        .eq('id', params.leagueId);

      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['draft'] });
      queryClient.invalidateQueries({ queryKey: ['league'] });
    },
  });
}
