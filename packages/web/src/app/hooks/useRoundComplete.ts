import { useQuery } from '@tanstack/react-query';
import { getPlayoffBracket } from '@sportsnot/nhl-api';
import { CURRENT_SEASON } from '@sportsnot/types';
import { useMockData } from '../../mock/MockDataProvider';
import { isAllSeriesComplete } from '../utils/roundUtils';

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
 * - Production mode: fetches the NHL playoff bracket and checks if all series
 *   in the given round are complete.
 */
export function useRoundComplete(currentRound: number): RoundCompleteResult {
  // Mock mode — always called to satisfy rules-of-hooks
  const { state } = useMockData();

  // Production mode — fetch bracket and derive completion
  const bracketQuery = useQuery({
    queryKey: ['playoff-bracket-round-complete', CURRENT_SEASON],
    queryFn: () => getPlayoffBracket(CURRENT_SEASON),
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

  const series = bracketQuery.data ?? [];
  const roundComplete =
    series.length > 0 && isAllSeriesComplete(series, currentRound);
  const seasonComplete = roundComplete && currentRound >= MAX_ROUND;

  return {
    roundComplete,
    seasonComplete,
    isLoading: bracketQuery.isLoading,
  };
}
