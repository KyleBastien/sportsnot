import { describe, it, expect } from '@rstest/core';
import { getEliminatedAbbreviations } from './useMockNhlApi';

describe('getEliminatedAbbreviations', () => {
  it('should return empty set for round 1 (no prior eliminations)', () => {
    const eliminated = getEliminatedAbbreviations(1);
    expect(eliminated.size).toBe(0);
  });

  it('should return 8 eliminated teams for round 2 (after round 1)', () => {
    const eliminated = getEliminatedAbbreviations(2);
    expect(eliminated.size).toBe(8);
    // Round 1 losers: OTT, TBL, MTL, NJD, STL, COL, MIN, LAK
    expect(eliminated.has('OTT')).toBe(true);
    expect(eliminated.has('TBL')).toBe(true);
    expect(eliminated.has('MTL')).toBe(true);
    expect(eliminated.has('NJD')).toBe(true);
    expect(eliminated.has('STL')).toBe(true);
    expect(eliminated.has('COL')).toBe(true);
    expect(eliminated.has('MIN')).toBe(true);
    expect(eliminated.has('LAK')).toBe(true);
  });

  it('should not include round 1 winners in eliminated set for round 2', () => {
    const eliminated = getEliminatedAbbreviations(2);
    // Round 1 winners: TOR, FLA, WSH, CAR, WPG, DAL, VGK, EDM
    expect(eliminated.has('TOR')).toBe(false);
    expect(eliminated.has('FLA')).toBe(false);
    expect(eliminated.has('WSH')).toBe(false);
    expect(eliminated.has('CAR')).toBe(false);
    expect(eliminated.has('WPG')).toBe(false);
    expect(eliminated.has('DAL')).toBe(false);
    expect(eliminated.has('VGK')).toBe(false);
    expect(eliminated.has('EDM')).toBe(false);
  });

  it('should return 12 eliminated teams for round 3 (after rounds 1+2)', () => {
    const eliminated = getEliminatedAbbreviations(3);
    expect(eliminated.size).toBe(12);
    // Round 2 losers added: TOR, WSH, WPG, VGK
    expect(eliminated.has('TOR')).toBe(true);
    expect(eliminated.has('WSH')).toBe(true);
    expect(eliminated.has('WPG')).toBe(true);
    expect(eliminated.has('VGK')).toBe(true);
    // Round 1 losers still present
    expect(eliminated.has('OTT')).toBe(true);
  });

  it('should return 14 eliminated teams for round 4 (after rounds 1+2+3)', () => {
    const eliminated = getEliminatedAbbreviations(4);
    expect(eliminated.size).toBe(14);
    // Round 3 losers added: CAR, DAL
    expect(eliminated.has('CAR')).toBe(true);
    expect(eliminated.has('DAL')).toBe(true);
    // Only FLA and EDM should survive
    expect(eliminated.has('FLA')).toBe(false);
    expect(eliminated.has('EDM')).toBe(false);
  });

  it('should scale correctly — round 2 survivors are not in round 3 eliminated unless lost in round 2', () => {
    const eliminated = getEliminatedAbbreviations(3);
    // FLA won round 2 → not eliminated
    expect(eliminated.has('FLA')).toBe(false);
    // CAR won round 2 → not eliminated before round 3
    expect(eliminated.has('CAR')).toBe(false);
    // DAL won round 2 → not eliminated before round 3
    expect(eliminated.has('DAL')).toBe(false);
    // EDM won round 2 → not eliminated before round 3
    expect(eliminated.has('EDM')).toBe(false);
  });
});
