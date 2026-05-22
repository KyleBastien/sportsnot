import { describe, it, expect } from '@rstest/core';
import {
  buildRoundSearch,
  clampRoundSelection,
  deriveCurrentRound,
  deriveNextRound,
  getAvailableRounds,
  getRoundPoints,
  isAllSeriesComplete,
  isRoundCompleteFromTeamStats,
  sumRoundPointsThroughRound,
} from './roundUtils';
import type { NHLPlayoffSeries } from '@sportsnot/types';

/** Helper to create a minimal series object for testing */
function makeSeries(
  round: number,
  topWins: number,
  bottomWins: number
): NHLPlayoffSeries {
  return {
    seriesCode: `R${round}-${topWins}-${bottomWins}`,
    round,
    topSeedTeam: { id: 1, name: 'Team A' },
    bottomSeedTeam: { id: 2, name: 'Team B' },
    topSeedWins: topWins,
    bottomSeedWins: bottomWins,
    isComplete: topWins === 4 || bottomWins === 4,
  };
}

function makeTeamStats(wins: number): { wins: number } {
  return { wins };
}

describe('roundUtils', () => {
  describe('deriveCurrentRound', () => {
    it('should use league.current_round when it is a positive number', () => {
      expect(deriveCurrentRound(2, 1)).toBe(2);
    });

    it('should fall back to completedDraftsCount when current_round is 0', () => {
      expect(deriveCurrentRound(0, 1)).toBe(1);
    });

    it('should fall back to completedDraftsCount when current_round is null', () => {
      expect(deriveCurrentRound(null, 2)).toBe(2);
    });

    it('should fall back to completedDraftsCount when current_round is undefined', () => {
      expect(deriveCurrentRound(undefined, 3)).toBe(3);
    });

    it('should return 0 when both are 0/undefined', () => {
      expect(deriveCurrentRound(0, 0)).toBe(0);
      expect(deriveCurrentRound(null, 0)).toBe(0);
      expect(deriveCurrentRound(undefined, 0)).toBe(0);
    });
  });

  describe('deriveNextRound', () => {
    it('should return 2 after Round 1 completes (current_round=0, 1 completed draft)', () => {
      expect(deriveNextRound(0, 1)).toBe(2);
    });

    it('should return 2 after Round 1 completes (current_round=null, 1 completed draft)', () => {
      expect(deriveNextRound(null, 1)).toBe(2);
    });

    it('should return 3 after Round 2 completes (current_round=0, 2 completed drafts)', () => {
      expect(deriveNextRound(0, 2)).toBe(3);
    });

    it('should return 3 when current_round is correctly set to 2', () => {
      expect(deriveNextRound(2, 2)).toBe(3);
    });

    it('should return 4 after Round 3 completes', () => {
      expect(deriveNextRound(0, 3)).toBe(4);
      expect(deriveNextRound(3, 3)).toBe(4);
    });

    it('should return 1 when no drafts have been completed (initial state)', () => {
      expect(deriveNextRound(0, 0)).toBe(1);
    });
  });

  describe('clampRoundSelection', () => {
    it('returns current round when selected round is missing', () => {
      expect(clampRoundSelection(undefined, 3)).toBe(3);
    });

    it('clamps values below round 1 up to 1', () => {
      expect(clampRoundSelection(0, 3)).toBe(1);
    });

    it('clamps values above current round down to current round', () => {
      expect(clampRoundSelection(4, 2)).toBe(2);
    });

    it('caps current round at the playoff max', () => {
      expect(clampRoundSelection(undefined, 8)).toBe(4);
    });
  });

  describe('getAvailableRounds', () => {
    it('returns rounds from 1 through current round', () => {
      expect(getAvailableRounds(3)).toEqual([1, 2, 3]);
    });

    it('caps available rounds at round 4', () => {
      expect(getAvailableRounds(8)).toEqual([1, 2, 3, 4]);
    });
  });

  describe('getRoundPoints', () => {
    it('reads numeric round keys', () => {
      expect(getRoundPoints({ 2: 7 }, 2)).toBe(7);
    });

    it('reads string round keys', () => {
      expect(getRoundPoints({ '3': 9 }, 3)).toBe(9);
    });

    it('defaults missing rounds to 0', () => {
      expect(getRoundPoints({}, 1)).toBe(0);
    });
  });

  describe('sumRoundPointsThroughRound', () => {
    it('sums all rounds through the selected round', () => {
      expect(sumRoundPointsThroughRound({ '1': 4, '2': 6, '3': 3 }, 2)).toBe(
        10
      );
    });

    it('treats missing rounds as 0', () => {
      expect(sumRoundPointsThroughRound({ '2': 6 }, 3)).toBe(6);
    });
  });

  describe('buildRoundSearch', () => {
    it('omits the search string for the current round', () => {
      expect(buildRoundSearch(3, 3)).toBe('');
    });

    it('includes the round query for historical rounds', () => {
      expect(buildRoundSearch(2, 3)).toBe('?round=2');
    });
  });

  describe('isAllSeriesComplete', () => {
    it('should return false when there are no series for the round', () => {
      expect(isAllSeriesComplete([], 1)).toBe(false);
    });

    it('should return false when no series match the given round', () => {
      const series = [makeSeries(2, 4, 1)];
      expect(isAllSeriesComplete(series, 1)).toBe(false);
    });

    it('should return true when all series in the round are complete', () => {
      const series = [
        makeSeries(1, 4, 2),
        makeSeries(1, 1, 4),
        makeSeries(1, 4, 3),
        makeSeries(1, 4, 0),
      ];
      expect(isAllSeriesComplete(series, 1)).toBe(true);
    });

    it('should return false when some series in the round are still in progress', () => {
      const series = [
        makeSeries(1, 4, 2),
        makeSeries(1, 3, 2), // not complete
        makeSeries(1, 4, 3),
      ];
      expect(isAllSeriesComplete(series, 1)).toBe(false);
    });

    it('should only check series for the specified round', () => {
      const series = [
        makeSeries(1, 4, 2),
        makeSeries(1, 4, 1),
        makeSeries(2, 2, 1), // round 2, not complete — should not affect round 1 check
      ];
      expect(isAllSeriesComplete(series, 1)).toBe(true);
      expect(isAllSeriesComplete(series, 2)).toBe(false);
    });

    it('should handle round 4 (Stanley Cup Final) with a single series', () => {
      const series = [makeSeries(4, 4, 3)];
      expect(isAllSeriesComplete(series, 4)).toBe(true);
    });

    it('should return false for round 4 when final is still in progress', () => {
      const series = [makeSeries(4, 3, 3)];
      expect(isAllSeriesComplete(series, 4)).toBe(false);
    });
  });

  describe('isRoundCompleteFromTeamStats', () => {
    it('should return false when there is no cached team data', () => {
      expect(isRoundCompleteFromTeamStats([])).toBe(false);
    });

    it('should return false when the round has an invalid team count', () => {
      expect(
        isRoundCompleteFromTeamStats([
          makeTeamStats(4),
          makeTeamStats(2),
          makeTeamStats(1),
        ])
      ).toBe(false);
    });

    it('should return true when half the teams in the round have 4 wins', () => {
      const teams = [
        makeTeamStats(4),
        makeTeamStats(4),
        makeTeamStats(4),
        makeTeamStats(4),
        makeTeamStats(0),
        makeTeamStats(2),
        makeTeamStats(3),
        makeTeamStats(1),
      ];

      expect(isRoundCompleteFromTeamStats(teams)).toBe(true);
    });

    it('should return false when some series are still in progress', () => {
      const teams = [
        makeTeamStats(4),
        makeTeamStats(4),
        makeTeamStats(3),
        makeTeamStats(2),
        makeTeamStats(2),
        makeTeamStats(1),
        makeTeamStats(0),
        makeTeamStats(0),
      ];

      expect(isRoundCompleteFromTeamStats(teams)).toBe(false);
    });

    it('should handle the final with two teams', () => {
      expect(
        isRoundCompleteFromTeamStats([makeTeamStats(4), makeTeamStats(2)])
      ).toBe(true);
      expect(
        isRoundCompleteFromTeamStats([makeTeamStats(3), makeTeamStats(2)])
      ).toBe(false);
    });
  });
});
