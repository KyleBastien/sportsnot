import { describe, it, expect } from '@rstest/core';
import {
  calculatePlayerPoints as calcEdge,
  calculateGoalieGamePoints as calcGoalieEdge,
  SCORING as EDGE_SCORING,
} from './scoring';
import { calculateGoalieGamePoints as calcGoalieRepo } from '@sportsnot/utils';
import { SCORING as REPO_SCORING } from '@sportsnot/types';
import { calculatePlayerPoints as calcRepo } from '@sportsnot/utils';

describe('edge/scoring parity with @sportsnot/utils', () => {
  it('SCORING constants match', () => {
    expect(EDGE_SCORING).toEqual(REPO_SCORING);
  });

  it('calculatePlayerPoints matches across a grid of inputs', () => {
    for (let g = 0; g < 10; g++) {
      for (let a = 0; a < 10; a++) {
        const stats = {
          playerId: 1,
          nhlSeason: '20252026',
          playoffRound: 1,
          goals: g,
          assists: a,
          gamesPlayed: g + a,
          isInjured: false,
          lastUpdated: '2025-01-01',
        };
        expect(calcEdge({ goals: g, assists: a })).toBe(calcRepo(stats));
      }
    }
  });

  it('calculateGoalieGamePoints matches across a grid of inputs', () => {
    for (let t = 0; t < 8; t++) {
      for (let o = 0; o < 8; o++) {
        expect(calcGoalieEdge(t, o)).toBe(calcGoalieRepo(t, o));
      }
    }
  });
});
