import { useQuery } from '@tanstack/react-query';
import {
  supabase,
  useLeague as useSupabaseLeague,
  usePlayoffPlayers as useSupabasePlayoffPlayers,
  usePlayoffTeams as useSupabasePlayoffTeams,
  useRegularSeasonPlayers as useSupabaseRegularSeasonPlayers,
} from '@sportsnot/supabase';
import {
  clampRoundSelection,
  sumRoundPointsThroughRound,
} from '../../utils/roundUtils';
import { useAuthContext } from '../../context/AuthContext';
import { useMockRoster } from '../../../mock/hooks/useMockRoster';
import { useMockLeague } from '../../../mock/hooks/useMockLeagues';
import {
  useMockPlayoffPlayers,
  useMockPlayoffTeams,
  useMockRegularSeasonPlayers,
} from '../../../mock/hooks/useMockNhlApi';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

interface RosterSlotRow {
  id: string;
  league_member_id: string;
  round: number;
  player_id: number | null;
  team_id: number | null;
  position: string;
  is_active: boolean;
  points_earned: number;
  activated_from_ir: boolean;
  is_eliminated?: boolean;
}

export function useMemberRoster(
  leagueId: string,
  leagueMemberId?: string,
  requestedRound?: number
) {
  const mockResult = useMockRoster(leagueId, leagueMemberId, requestedRound);
  const { user } = useAuthContext();

  const queryResult = useQuery({
    queryKey: ['roster', leagueId, leagueMemberId ?? user?.id, requestedRound],
    queryFn: async () => {
      let memberId = leagueMemberId;
      let memberTotalPoints = 0;
      let memberRoundPoints: Record<string, number> | null = null;

      if (memberId) {
        const { data: member } = await supabase
          .from('league_members')
          .select('id, total_points, round_points')
          .eq('id', memberId)
          .single();

        if (!member) throw new Error('Member not found');
        memberTotalPoints = member.total_points ?? 0;
        memberRoundPoints = member.round_points;
      } else {
        const { data: member } = await supabase
          .from('league_members')
          .select('id, total_points, round_points')
          .eq('league_id', leagueId)
          .eq('user_id', user!.id)
          .single();

        if (!member) throw new Error('Not a member of this league');
        memberId = member.id;
        memberTotalPoints = member.total_points ?? 0;
        memberRoundPoints = member.round_points;
      }

      const { data: league } = await supabase
        .from('leagues')
        .select('current_round')
        .eq('id', leagueId)
        .single();

      if (!league) throw new Error('League not found');
      const currentRound = Math.max(league.current_round ?? 1, 1);
      const selectedRound = clampRoundSelection(
        requestedRound ?? currentRound,
        currentRound
      );

      const { data: roster, error } = await supabase
        .from('rosters')
        .select('*')
        .eq('league_member_id', memberId)
        .eq('round', selectedRound);

      if (error) throw error;

      return {
        memberId: memberId as string,
        currentRound,
        round: selectedRound,
        slots: (roster ?? []).map((s: RosterSlotRow) => ({
          ...s,
          is_eliminated: s.is_eliminated ?? false,
        })),
        totalPoints:
          selectedRound === currentRound
            ? memberTotalPoints
            : sumRoundPointsThroughRound(memberRoundPoints, selectedRound),
        isHistorical: selectedRound !== currentRound,
      };
    },
    enabled: !IS_MOCK && !!user,
  });

  return IS_MOCK ? mockResult : queryResult;
}

export function useLeagueForRoster(leagueId: string | undefined) {
  const mockResult = useMockLeague(leagueId);
  const supabaseResult = useSupabaseLeague(leagueId);
  return IS_MOCK ? mockResult : supabaseResult;
}

export function usePlayoffPlayersForRoster(season: string, round: number) {
  const mockResult = useMockPlayoffPlayers(season, round);
  const supabaseResult = useSupabasePlayoffPlayers(season, round);
  return IS_MOCK ? mockResult : supabaseResult;
}

export function usePlayoffTeamsForRoster(season: string, round: number) {
  const mockResult = useMockPlayoffTeams(season, round);
  const supabaseResult = useSupabasePlayoffTeams(season, round);
  return IS_MOCK ? mockResult : supabaseResult;
}

export function useRegularSeasonPlayersForRoster(
  season: string,
  enabled: boolean
) {
  const mockResult = useMockRegularSeasonPlayers(season, enabled);
  const supabaseResult = useSupabaseRegularSeasonPlayers(season, enabled);
  return IS_MOCK ? mockResult : supabaseResult;
}
