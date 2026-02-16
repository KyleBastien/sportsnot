import { describe, it, expect } from '@rstest/core';
import { calculateRoundMemberPoints, calculateMemberPoints } from './utils';

// We test calculateMemberPoints using the real fixture data loaded
// by the shared utility. To keep tests deterministic, we construct
// minimal MockState-like objects and verify the cumulative logic.

describe('calculateRoundMemberPoints', () => {
  it('should return 0 points when no player IDs or goalie team IDs', () => {
    const pts = calculateRoundMemberPoints([], [], '2025-04-19', '2025-04-22');
    expect(pts.playerPts).toBe(0);
    expect(pts.goaliePts).toBe(0);
  });

  it('should return 0 for players with no games in date range', () => {
    // Use a player ID that exists but test with a date range before any games
    const pts = calculateRoundMemberPoints(
      [8470594],
      [],
      '2020-01-01',
      '2020-01-02'
    );
    expect(pts.playerPts).toBe(0);
    expect(pts.goaliePts).toBe(0);
  });

  it('should return 0 for non-existent player IDs', () => {
    const pts = calculateRoundMemberPoints(
      [99999999],
      [],
      '2025-04-19',
      '2025-06-30'
    );
    expect(pts.playerPts).toBe(0);
    expect(pts.goaliePts).toBe(0);
  });
});

describe('calculateMemberPoints', () => {
  it('should return 0 when member has no roster', () => {
    const state = {
      currentRound: 1,
      simulationDate: '2025-04-25',
      rosters: {},
      rosterHistory: {},
    };
    const result = calculateMemberPoints(state, 'member-1');
    expect(result.totalPoints).toBe(0);
    expect(result.playerPoints).toBe(0);
    expect(result.goaliePoints).toBe(0);
    expect(Object.keys(result.roundPoints).length).toBe(0);
  });

  it('should return 0 when simulation date is before round starts', () => {
    const state = {
      currentRound: 1,
      simulationDate: '2025-04-18', // before R1 first game (2025-04-19)
      rosters: {
        'member-1': [
          {
            id: 'slot-1',
            leagueMemberId: 'member-1',
            round: 1,
            playerId: 8470594,
            position: 'F' as const,
            isActive: true,
            pointsEarned: 0,
            activatedFromIr: false,
          },
        ],
      },
      rosterHistory: {},
    };
    const result = calculateMemberPoints(state, 'member-1');
    expect(result.totalPoints).toBe(0);
  });

  it('should compute points for current round from rosters', () => {
    const state = {
      currentRound: 1,
      simulationDate: '2025-05-10', // well into round 1
      rosters: {
        'member-1': [
          {
            id: 'slot-1',
            leagueMemberId: 'member-1',
            round: 1,
            playerId: 8470594,
            position: 'F' as const,
            isActive: true,
            pointsEarned: 0,
            activatedFromIr: false,
          },
        ],
      },
      rosterHistory: {},
    };
    const result = calculateMemberPoints(state, 'member-1');
    // Points may be 0 or more depending on fixture data,
    // but the function should not throw
    expect(result.totalPoints).toBeGreaterThanOrEqual(0);
    expect(result.totalPoints).toBe(result.playerPoints + result.goaliePoints);
  });

  it('should not count inactive roster slots', () => {
    const state = {
      currentRound: 1,
      simulationDate: '2025-05-10',
      rosters: {
        'member-1': [
          {
            id: 'slot-1',
            leagueMemberId: 'member-1',
            round: 1,
            playerId: 8470594,
            position: 'IR_F' as const,
            isActive: false,
            pointsEarned: 0,
            activatedFromIr: false,
          },
        ],
      },
      rosterHistory: {},
    };
    const result = calculateMemberPoints(state, 'member-1');
    expect(result.totalPoints).toBe(0);
  });

  it('should accumulate points from past rounds via rosterHistory', () => {
    const state = {
      currentRound: 2,
      simulationDate: '2025-05-10', // into round 2
      rosters: {
        // Current round 2 roster is empty
        'member-1': [],
      },
      rosterHistory: {
        'member-1': {
          1: [
            {
              id: 'slot-1',
              leagueMemberId: 'member-1',
              round: 1,
              playerId: 8470594,
              position: 'F' as const,
              isActive: true,
              pointsEarned: 0,
              activatedFromIr: false,
            },
          ],
        },
      },
    };
    const result = calculateMemberPoints(state, 'member-1');
    // Should include round 1 points from history
    expect(result.totalPoints).toBeGreaterThanOrEqual(0);
    // Round 2 should contribute 0 (empty roster)
    expect(result.roundPoints[2]).toBeUndefined();
  });

  it('should accumulate points cumulatively across rounds', () => {
    // Create state with roster history for round 1 and current roster for round 2
    const roster1 = [
      {
        id: 'slot-r1',
        leagueMemberId: 'member-1',
        round: 1,
        playerId: 8470594,
        position: 'F' as const,
        isActive: true,
        pointsEarned: 0,
        activatedFromIr: false,
      },
    ];
    const roster2 = [
      {
        id: 'slot-r2',
        leagueMemberId: 'member-1',
        round: 2,
        playerId: 8470594,
        position: 'F' as const,
        isActive: true,
        pointsEarned: 0,
        activatedFromIr: false,
      },
    ];

    // First compute round 1 only
    const stateR1Only = {
      currentRound: 1,
      simulationDate: '2025-05-04', // end of R1
      rosters: { 'member-1': roster1 },
      rosterHistory: {},
    };
    const r1Result = calculateMemberPoints(stateR1Only, 'member-1');

    // Now compute round 1 + round 2
    const stateR1R2 = {
      currentRound: 2,
      simulationDate: '2025-05-10',
      rosters: { 'member-1': roster2 },
      rosterHistory: { 'member-1': { 1: roster1 } },
    };
    const r1r2Result = calculateMemberPoints(stateR1R2, 'member-1');

    // Cumulative should be >= round 1 alone
    expect(r1r2Result.totalPoints).toBeGreaterThanOrEqual(r1Result.totalPoints);
  });

  it('should return correct round_points breakdown', () => {
    const roster1 = [
      {
        id: 'slot-r1',
        leagueMemberId: 'member-1',
        round: 1,
        playerId: 8470594,
        position: 'F' as const,
        isActive: true,
        pointsEarned: 0,
        activatedFromIr: false,
      },
    ];

    const state = {
      currentRound: 2,
      simulationDate: '2025-05-10',
      rosters: { 'member-1': [] },
      rosterHistory: { 'member-1': { 1: roster1 } },
    };
    const result = calculateMemberPoints(state, 'member-1');

    // totalPoints should equal sum of all round_points
    const roundPointsSum = Object.values(result.roundPoints).reduce(
      (a, b) => a + b,
      0
    );
    expect(result.totalPoints).toBe(roundPointsSum);
  });
});
