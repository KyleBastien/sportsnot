import { useQuery } from '@tanstack/react-query';
import { supabase } from '@sportsnot/supabase';
import { CURRENT_SEASON } from '@sportsnot/types';
import { useMockData } from '../../mock/MockDataProvider';
import { isRoundCompleteFromTeamStats } from '../utils/roundUtils';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';
const MAX_ROUND = 4;

export interface RoundCompleteResult {
  roundComplete: boolean;
  seasonComplete: boolean;
  isLoading: boolean;
}

/**
 * Hook to determine whether the current playoff round is complete.
 *
 * - Mock mode: reads `roundComplete` / `seasonComplete` from MockDataProvider state.
 * - Production mode: reads cached round win totals from `team_stats_cache` and
 *   checks if exactly half the teams in the round have reached 4 wins.
 */
export function useRoundComplete(currentRound: number): RoundCompleteResult {
  // Mock mode — always called to satisfy rules-of-hooks
  const { state } = useMockData();

  // Production mode — read cached round win totals from Supabase
  const teamStatsQuery = useQuery({
    queryKey: ['round-complete-team-stats', CURRENT_SEASON, currentRound],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('team_stats_cache')
        .select('wins')
        .eq('nhl_season', CURRENT_SEASON)
        .eq('playoff_round', currentRound);

      if (error) throw error;
      return data ?? [];
    },
    enabled: !IS_MOCK && currentRound >= 1 && currentRound <= MAX_ROUND,
    staleTime: 1000 * 60 * 2, // 2 min cache
    refetchInterval: 1000 * 60 * 5, // re-check every 5 min
  });

  if (IS_MOCK) {
    // Derive round/season completion by comparing simulation state to the
    // league's current round:
    // - sim ahead of league → league's round already completed
    // - sim matches league  → use the live roundComplete flag
    // - sim behind league   → league advanced via draft; round not yet complete
    const roundDone =
      state.currentRound > currentRound ||
      (state.currentRound === currentRound && state.roundComplete);
    return {
      roundComplete: roundDone,
      seasonComplete:
        state.currentRound >= currentRound && state.seasonComplete,
      isLoading: false,
    };
  }

  const teams = teamStatsQuery.data ?? [];
  const roundComplete = isRoundCompleteFromTeamStats(teams);
  const seasonComplete = roundComplete && currentRound >= MAX_ROUND;

  return {
    roundComplete,
    seasonComplete,
    isLoading: teamStatsQuery.isLoading,
  };
}
