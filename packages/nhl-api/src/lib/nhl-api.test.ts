import { describe, it, expect } from '@rstest/core';
import { getEliminatedTeams } from './nhl-api';
import type { NHLPlayoffSeries } from '@sportsnot/types';

describe('getEliminatedTeams', () => {
  it('should return empty set when no series are complete', () => {
    const series: NHLPlayoffSeries[] = [
      {
        seriesCode: 'A',
        round: 1,
        topSeedTeam: { id: 1, name: 'Team A' },
        bottomSeedTeam: { id: 2, name: 'Team B' },
        topSeedWins: 2,
        bottomSeedWins: 1,
        isComplete: false,
      },
    ];
    expect(getEliminatedTeams(series).size).toBe(0);
  });

  it('should identify bottom seed as eliminated when top seed wins 4', () => {
    const series: NHLPlayoffSeries[] = [
      {
        seriesCode: 'A',
        round: 1,
        topSeedTeam: { id: 1, name: 'Team A' },
        bottomSeedTeam: { id: 2, name: 'Team B' },
        topSeedWins: 4,
        bottomSeedWins: 2,
        isComplete: true,
      },
    ];
    const eliminated = getEliminatedTeams(series);
    expect(eliminated.has(2)).toBe(true);
    expect(eliminated.has(1)).toBe(false);
  });

  it('should identify top seed as eliminated when bottom seed wins 4', () => {
    const series: NHLPlayoffSeries[] = [
      {
        seriesCode: 'A',
        round: 1,
        topSeedTeam: { id: 1, name: 'Team A' },
        bottomSeedTeam: { id: 2, name: 'Team B' },
        topSeedWins: 3,
        bottomSeedWins: 4,
        isComplete: true,
      },
    ];
    const eliminated = getEliminatedTeams(series);
    expect(eliminated.has(1)).toBe(true);
    expect(eliminated.has(2)).toBe(false);
  });

  it('should handle multiple completed series', () => {
    const series: NHLPlayoffSeries[] = [
      {
        seriesCode: 'A',
        round: 1,
        topSeedTeam: { id: 1, name: 'Team A' },
        bottomSeedTeam: { id: 2, name: 'Team B' },
        topSeedWins: 4,
        bottomSeedWins: 1,
        isComplete: true,
      },
      {
        seriesCode: 'B',
        round: 1,
        topSeedTeam: { id: 3, name: 'Team C' },
        bottomSeedTeam: { id: 4, name: 'Team D' },
        topSeedWins: 2,
        bottomSeedWins: 4,
        isComplete: true,
      },
    ];
    const eliminated = getEliminatedTeams(series);
    expect(eliminated.size).toBe(2);
    expect(eliminated.has(2)).toBe(true); // B eliminated
    expect(eliminated.has(3)).toBe(true); // C eliminated
  });

  it('should skip series without team data', () => {
    const series: NHLPlayoffSeries[] = [
      {
        seriesCode: 'A',
        round: 1,
        topSeedWins: 4,
        bottomSeedWins: 0,
        isComplete: true,
      },
    ];
    expect(getEliminatedTeams(series).size).toBe(0);
  });
});
