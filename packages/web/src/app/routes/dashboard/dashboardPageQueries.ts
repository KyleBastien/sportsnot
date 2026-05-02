import { useQuery } from '@tanstack/react-query';
import { supabase } from '@sportsnot/supabase';
import { CURRENT_SEASON } from '@sportsnot/types';
import { useAuthContext } from '../../context/AuthContext';
import { useMockMyLeagues } from '../../../mock/hooks/useMockLeagues';
import { useMockLiveGamesTeamStats } from '../../../mock/hooks/useMockLiveGames';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

interface LeagueWithMembership {
  id: string;
  name: string;
  status: string;
  current_round: number;
  max_participants: number;
  commissioner_id: string;
  invite_code: string;
  league_members: Array<{
    team_name: string;
    total_points: number;
    user_id: string;
  }>;
  memberCount: number;
}

interface TeamStatRow {
  team_id: number;
  team_name: string;
  team_abbreviation: string;
  wins: number;
  shutouts: number;
  is_eliminated: boolean;
  playoff_round: number;
}

export function useLiveGames() {
  const mockResult = useMockLiveGamesTeamStats();

  const queryResult = useQuery({
    queryKey: ['live-games'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('team_stats_cache')
        .select(
          'team_id, team_name, team_abbreviation, wins, shutouts, is_eliminated, playoff_round'
        )
        .eq('nhl_season', CURRENT_SEASON)
        .eq('is_eliminated', false)
        .order('playoff_round', { ascending: false })
        .order('wins', { ascending: false });

      if (error) throw error;

      const latestByTeam = new Map<number, TeamStatRow>();
      for (const team of (data ?? []) as TeamStatRow[]) {
        if (!latestByTeam.has(team.team_id)) {
          latestByTeam.set(team.team_id, team);
        }
      }

      return [...latestByTeam.values()];
    },
    enabled: !IS_MOCK,
  });

  return IS_MOCK ? mockResult : queryResult;
}

export function useMyLeagues() {
  const mockResult = useMockMyLeagues();
  const { user } = useAuthContext();

  const queryResult = useQuery({
    queryKey: ['my-leagues', user?.id],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('leagues')
        .select(
          `
          *,
          league_members!inner(team_name, total_points, user_id)
        `
        )
        .eq('league_members.user_id', user!.id);

      if (error) throw error;

      return (data ?? []).map(
        (league: {
          league_members?: {
            team_name: string;
            total_points: number;
            user_id: string;
          }[];
        }) => ({
          ...league,
          memberCount: league.league_members?.length ?? 0,
        })
      ) as LeagueWithMembership[];
    },
    enabled: !IS_MOCK && !!user,
  });

  return IS_MOCK ? mockResult : queryResult;
}
