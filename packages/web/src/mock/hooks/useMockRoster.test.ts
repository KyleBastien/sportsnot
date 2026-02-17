import { describe, it, expect } from '@rstest/core';
import { calculateSlotPoints } from './useMockRoster';
import { calculateRoundMemberPoints, calculateMemberPoints } from '../utils';
import { getRoundDateBounds } from '../MockDataProvider';

// Round date bounds (from fixture data):
// R1: 2025-04-19 to 2025-05-04
// R2: 2025-05-05 to 2025-05-18
// R3 (CF): 2025-05-20 to 2025-05-29
// R4 (SCF): 2025-06-04 to 2025-06-17

// Player 8470594 has R1 game logs (e.g. 2025-04-29)

describe('calculateSlotPoints', () => {
  it('should return 0 when round has no date bounds', () => {
    const pts = calculateSlotPoints(
      { round: 99, playerId: 8470594 },
      '2025-05-10'
    );
    expect(pts).toBe(0);
  });

  it('should return 0 when simulationDate is before round starts', () => {
    // R1 starts 2025-04-19; simulation at 2025-04-18
    const pts = calculateSlotPoints(
      { round: 1, playerId: 8470594 },
      '2025-04-18'
    );
    expect(pts).toBe(0);
  });

  it('should return 0 when slot has no player or team', () => {
    const pts = calculateSlotPoints({ round: 1 }, '2025-05-10');
    expect(pts).toBe(0);
  });

  it('should compute only R1 points for a round-1 slot', () => {
    const bounds = getRoundDateBounds(1)!;
    // Get the full R1 points using calculateRoundMemberPoints
    const expected = calculateRoundMemberPoints(
      [8470594],
      [],
      bounds.firstDate,
      bounds.lastDate
    );

    // calculateSlotPoints with sim date well past R1 should cap at R1 bounds
    const pts = calculateSlotPoints(
      { round: 1, playerId: 8470594 },
      '2025-05-20' // past R1
    );
    expect(pts).toBe(expected.playerPts);
  });

  it('should NOT include R1 game points for a round-2 slot', () => {
    const boundsR1 = getRoundDateBounds(1)!;
    const boundsR2 = getRoundDateBounds(2)!;

    // Points using cumulative (old bug: no lower bound)
    const cumulativePts = calculateRoundMemberPoints(
      [8470594],
      [],
      boundsR1.firstDate,
      boundsR2.lastDate
    );

    // Points using round-2-only bounds
    const r2OnlyPts = calculateSlotPoints(
      { round: 2, playerId: 8470594 },
      boundsR2.lastDate
    );

    // R2-only should NOT include R1 points
    // If the player scored in R1, cumulative would be higher
    const r1Pts = calculateRoundMemberPoints(
      [8470594],
      [],
      boundsR1.firstDate,
      boundsR1.lastDate
    );

    if (r1Pts.playerPts > 0) {
      expect(r2OnlyPts).toBeLessThan(
        cumulativePts.playerPts + cumulativePts.goaliePts
      );
    }
    // R2 slot should only have R2-bounded points
    const expectedR2 = calculateRoundMemberPoints(
      [8470594],
      [],
      boundsR2.firstDate,
      boundsR2.lastDate
    );
    expect(r2OnlyPts).toBe(expectedR2.playerPts);
  });

  it('should respect simulationDate within a round', () => {
    const bounds = getRoundDateBounds(1)!;
    // Simulate mid-R1
    const midDate = '2025-04-25';

    const ptsMid = calculateSlotPoints(
      { round: 1, playerId: 8470594 },
      midDate
    );
    const ptsFull = calculateSlotPoints(
      { round: 1, playerId: 8470594 },
      bounds.lastDate
    );

    // Mid-round points should be <= full round points
    expect(ptsMid).toBeLessThanOrEqual(ptsFull);
  });

  it('should compute goalie points using teamId when no playerId', () => {
    // Team 13 = FLA (Florida Panthers)
    const bounds = getRoundDateBounds(1)!;
    const expected = calculateRoundMemberPoints(
      [],
      [13],
      bounds.firstDate,
      bounds.lastDate
    );

    const pts = calculateSlotPoints({ round: 1, teamId: 13 }, '2025-05-20');
    expect(pts).toBe(expected.goaliePts);
  });

  it('should use playerId for player points even when teamId is present', () => {
    // When both playerId and teamId are set, should use playerId (player, not goalie)
    const bounds = getRoundDateBounds(1)!;
    const expectedPlayer = calculateRoundMemberPoints(
      [8470594],
      [],
      bounds.firstDate,
      bounds.lastDate
    );

    const pts = calculateSlotPoints(
      { round: 1, playerId: 8470594, teamId: 13 },
      '2025-05-20'
    );
    expect(pts).toBe(expectedPlayer.playerPts);
  });
});

// ── totalPoints contract (US-002) ──────────────────────────────────────
// These tests verify the calculateMemberPoints function returns the
// correct totalPoints that useMockRoster now exposes.

describe('totalPoints from calculateMemberPoints (useMockRoster contract)', () => {
  const makeSlot = (
    round: number,
    playerId: number,
    memberId = 'member-1'
  ) => ({
    id: `slot-r${round}-${playerId}`,
    leagueMemberId: memberId,
    round,
    playerId,
    position: 'F' as const,
    isActive: true,
    pointsEarned: 0,
    activatedFromIr: false,
  });

  it('should equal sum of slot points in Round 1', () => {
    const roster = [makeSlot(1, 8470594)];
    const state = {
      currentRound: 1,
      simulationDate: '2025-05-04', // end of R1
      rosters: { 'member-1': roster },
      rosterHistory: {},
    };

    const result = calculateMemberPoints(state, 'member-1');
    const slotPtsSum = roster.reduce(
      (sum, s) => sum + calculateSlotPoints(s, state.simulationDate),
      0
    );

    // In R1 totalPoints equals the sum of current round slot points
    expect(result.totalPoints).toBe(slotPtsSum);
  });

  it('should include prior rounds in R2+', () => {
    const rosterR1 = [makeSlot(1, 8470594)];
    const rosterR2 = [makeSlot(2, 8470594)];

    // R1-only totalPoints
    const stateR1 = {
      currentRound: 1,
      simulationDate: '2025-05-04',
      rosters: { 'member-1': rosterR1 },
      rosterHistory: {},
    };
    const r1Total = calculateMemberPoints(stateR1, 'member-1').totalPoints;

    // R2 totalPoints should include R1 contributions from rosterHistory
    const stateR2 = {
      currentRound: 2,
      simulationDate: '2025-05-18', // end of R2
      rosters: { 'member-1': rosterR2 },
      rosterHistory: { 'member-1': { 1: rosterR1 } },
    };
    const r2Total = calculateMemberPoints(stateR2, 'member-1').totalPoints;

    // Cumulative total should be >= R1 total
    expect(r2Total).toBeGreaterThanOrEqual(r1Total);
  });

  it('should return totalPoints as playerPoints + goaliePoints', () => {
    const roster = [
      makeSlot(1, 8470594), // player
      {
        id: 'slot-g1',
        leagueMemberId: 'member-1',
        round: 1,
        playerId: undefined as unknown as number,
        teamId: 13, // FLA goalie
        position: 'G' as const,
        isActive: true,
        pointsEarned: 0,
        activatedFromIr: false,
      },
    ];
    const state = {
      currentRound: 1,
      simulationDate: '2025-05-04',
      rosters: { 'member-1': roster },
      rosterHistory: {},
    };
    const result = calculateMemberPoints(state, 'member-1');
    expect(result.totalPoints).toBe(result.playerPoints + result.goaliePoints);
  });

  it('should have roundPoints that sum to totalPoints', () => {
    const rosterR1 = [makeSlot(1, 8470594)];
    const rosterR2 = [makeSlot(2, 8470594)];
    const state = {
      currentRound: 2,
      simulationDate: '2025-05-18',
      rosters: { 'member-1': rosterR2 },
      rosterHistory: { 'member-1': { 1: rosterR1 } },
    };
    const result = calculateMemberPoints(state, 'member-1');
    const roundSum = Object.values(result.roundPoints).reduce(
      (a, b) => a + b,
      0
    );
    expect(result.totalPoints).toBe(roundSum);
  });
});
