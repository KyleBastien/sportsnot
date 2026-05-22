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
const LEAGUE_MEMBER_POINTS_SELECT = 'id, total_points, round_points';
const LEAGUE_CURRENT_ROUND_SELECT = 'current_round';

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
      const member = await fetchRosterMember(
        leagueId,
        leagueMemberId,
        user?.id
      );
      const currentRound = await fetchLeagueCurrentRound(leagueId);
      const selectedRound = clampRoundSelection(
        requestedRound ?? currentRound,
        currentRound
      );
      const roster = await fetchRosterSlots(member.id, selectedRound);

      return {
        memberId: member.id,
        currentRound,
        round: selectedRound,
        slots: normalizeRosterSlots(roster),
        totalPoints:
          selectedRound === currentRound
            ? (member.total_points ?? 0)
            : sumRoundPointsThroughRound(member.round_points, selectedRound),
        isHistorical: selectedRound !== currentRound,
      };
    },
    enabled: !IS_MOCK && !!user,
  });

  return IS_MOCK ? mockResult : queryResult;
}

async function fetchRosterMember(
  leagueId: string,
  leagueMemberId: string | undefined,
  userId: string | undefined
) {
  const query = supabase
    .from('league_members')
    .select(LEAGUE_MEMBER_POINTS_SELECT);

  const { data: member } = leagueMemberId
    ? await query.eq('id', leagueMemberId).single()
    : await query.eq('league_id', leagueId).eq('user_id', userId!).single();

  if (!member) {
    throw new Error(
      leagueMemberId ? 'Member not found' : 'Not a member of this league'
    );
  }

  return member;
}

async function fetchLeagueCurrentRound(leagueId: string) {
  const { data: league } = await supabase
    .from('leagues')
    .select(LEAGUE_CURRENT_ROUND_SELECT)
    .eq('id', leagueId)
    .single();

  if (!league) {
    throw new Error('League not found');
  }

  return Math.max(league.current_round ?? 1, 1);
}

async function fetchRosterSlots(leagueMemberId: string, round: number) {
  const { data: roster, error } = await supabase
    .from('rosters')
    .select('*')
    .eq('league_member_id', leagueMemberId)
    .eq('round', round);

  if (error) {
    throw error;
  }

  return roster ?? [];
}

function normalizeRosterSlots(roster: RosterSlotRow[]) {
  return roster.map((slot) => ({
    ...slot,
    is_eliminated: slot.is_eliminated ?? false,
  }));
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
