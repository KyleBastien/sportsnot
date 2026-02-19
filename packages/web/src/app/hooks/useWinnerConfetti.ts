import { useEffect } from 'react';
import confetti from 'canvas-confetti';

/**
 * Fires a confetti burst when the current user is the league winner.
 * Triggers once per session per league (tracked via sessionStorage).
 */
export function useWinnerConfetti({
  seasonComplete,
  isWinner,
  leagueId,
}: {
  seasonComplete: boolean;
  isWinner: boolean;
  leagueId: string | undefined;
}): void {
  useEffect(() => {
    if (!seasonComplete || !isWinner || !leagueId) return;

    const key = `confetti-shown-${leagueId}`;
    if (sessionStorage.getItem(key)) return;

    sessionStorage.setItem(key, '1');

    const end = Date.now() + 3_000;

    function frame() {
      confetti({
        particleCount: 3,
        angle: 60,
        spread: 55,
        origin: { x: 0 },
      });
      confetti({
        particleCount: 3,
        angle: 120,
        spread: 55,
        origin: { x: 1 },
      });
      if (Date.now() < end) {
        requestAnimationFrame(frame);
      }
    }

    frame();
  }, [seasonComplete, isWinner, leagueId]);
}
