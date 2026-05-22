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

const ID_COLUMN = 'id';
const LEAGUE_ID_COLUMN = 'league_id';
const LEAGUE_MEMBER_POINTS_SELECT = 'id, total_points, round_points';
const LEAGUE_CURRENT_ROUND_SELECT = 'current_round';
const LEAGUES_TABLE = 'leagues';
const LEAGUE_MEMBERS_TABLE = 'league_members';
const LEAGUE_MEMBER_ID_COLUMN = 'league_member_id';
const LEAGUE_NOT_FOUND_ERROR = 'League not found';
const MEMBER_NOT_FOUND_ERROR = 'Member not found';
const MOCK_MODE_ENABLED = 'true';
const NOT_LEAGUE_MEMBER_ERROR = 'Not a member of this league';
const ROSTERS_SELECT = '*';
const ROSTERS_TABLE = 'rosters';
const ROSTER_QUERY_KEY = 'roster';
const ROUND_COLUMN = 'round';
const USER_ID_COLUMN = 'user_id';
const IS_MOCK = import.meta.env.VITE_MOCK_MODE === MOCK_MODE_ENABLED;

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

export function useMemberRoster(params: {
  leagueId: string;
  leagueMemberId?: string;
  requestedRound?: number;
}) {
  const { leagueId, leagueMemberId, requestedRound } = params;
  const mockResult = useMockRoster(leagueId, leagueMemberId, requestedRound);
  const { user } = useAuthContext();

  const queryResult = useQuery({
    queryKey: [
      ROSTER_QUERY_KEY,
      leagueId,
      leagueMemberId ?? user?.id,
      requestedRound,
    ],
    queryFn: async () => {
      const member = await fetchRosterMember({
        leagueId,
        leagueMemberId,
        userId: user?.id,
      });
      const currentRound = await fetchLeagueCurrentRound({ leagueId });
      const selectedRound = clampRoundSelection(
        requestedRound ?? currentRound,
        currentRound
      );
      const roster = await fetchRosterSlots({
        leagueMemberId: member.id,
        round: selectedRound,
      });

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

async function fetchRosterMember(params: {
  leagueId: string;
  leagueMemberId: string | undefined;
  userId: string | undefined;
}) {
  const { leagueId, leagueMemberId, userId } = params;
  const query = supabase
    .from(LEAGUE_MEMBERS_TABLE)
    .select(LEAGUE_MEMBER_POINTS_SELECT);

  const { data: member } = leagueMemberId
    ? await query.eq(ID_COLUMN, leagueMemberId).single()
    : await query
        .eq(LEAGUE_ID_COLUMN, leagueId)
        .eq(USER_ID_COLUMN, userId!)
        .single();

  if (!member) {
    throw new Error(
      leagueMemberId ? MEMBER_NOT_FOUND_ERROR : NOT_LEAGUE_MEMBER_ERROR
    );
  }

  return member;
}

async function fetchLeagueCurrentRound(params: { leagueId: string }) {
  const { leagueId } = params;
  const { data: league } = await supabase
    .from(LEAGUES_TABLE)
    .select(LEAGUE_CURRENT_ROUND_SELECT)
    .eq(ID_COLUMN, leagueId)
    .single();

  if (!league) {
    throw new Error(LEAGUE_NOT_FOUND_ERROR);
  }

  return Math.max(league.current_round ?? 1, 1);
}

async function fetchRosterSlots(params: {
  leagueMemberId: string;
  round: number;
}) {
  const { leagueMemberId, round } = params;
  const { data: roster, error } = await supabase
    .from(ROSTERS_TABLE)
    .select(ROSTERS_SELECT)
    .eq(LEAGUE_MEMBER_ID_COLUMN, leagueMemberId)
    .eq(ROUND_COLUMN, round);

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
