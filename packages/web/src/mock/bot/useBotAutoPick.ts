import { useEffect, useRef } from 'react';
import { useMockData } from '../MockDataProvider';
import { selectBotPick, getCurrentBotUserId, getBotMemberId } from './autoPick';
import type { DraftPick, Position } from '@sportsnot/types';

/**
 * Hook that auto-picks for bots during a mock draft.
 * When it's a bot's turn, waits 1-2 seconds then dispatches MAKE_PICK.
 * Should be rendered inside MockDataProvider when a draft is active.
 */
export function useBotAutoPick(): void {
  const { state, dispatch } = useMockData();
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    // Clean up any pending timer
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }

    const botUserId = getCurrentBotUserId(state);
    if (!botUserId) return;

    const ds = state.draftState;
    if (!ds) return;

    const memberId = getBotMemberId(state, botUserId);
    if (!memberId) return;

    const result = selectBotPick(ds, botUserId);
    if (!result) return;

    // Delay 1-2 seconds (random for realistic feel)
    const delay = 1000 + Math.random() * 1000;

    timerRef.current = setTimeout(() => {
      timerRef.current = null;

      const pick: DraftPick = {
        id: `mock-pick-${ds.draft.id}-${ds.draft.currentPick}`,
        draftId: ds.draft.id,
        leagueMemberId: memberId,
        pickNumber: ds.draft.currentPick,
        playerId: result.position === 'G' ? undefined : result.playerId,
        teamId: result.position === 'G' ? result.playerId : undefined,
        position: result.position as Position,
        pickedAt: new Date().toISOString(),
      };

      dispatch({ type: 'MAKE_PICK', payload: { pick } });
    }, delay);

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [state, dispatch]);
}
