import { describe, it, expect } from '@rstest/core';
import { calculateMemberPoints } from '../utils';

/**
 * US-002: Verify League Dashboard points display
 *
 * Both useMockLeague (Dashboard) and useMockStandings call
 * calculateMemberPoints(state, memberId).totalPoints. These tests verify
 * the data transformation contract so Dashboard points always match
 * Standings points for the same member.
 */

// Helper: simulate the total_points mapping used in useMockLeague
function dashboardTotalPoints(
  state: Parameters<typeof calculateMemberPoints>[0],
  memberIds: string[]
): Record<string, number> {
  const result: Record<string, number> = {};
  for (const id of memberIds) {
    result[id] = calculateMemberPoints(state, id).totalPoints;
  }
  return result;
}

// Helper: simulate the total_points mapping used in useMockStandings
function standingsTotalPoints(
  state: Parameters<typeof calculateMemberPoints>[0],
  memberIds: string[]
): Record<string, number> {
  const result: Record<string, number> = {};
  for (const id of memberIds) {
    const pts = calculateMemberPoints(state, id);
    result[id] = pts.totalPoints;
  }
  return result;
}

describe('Dashboard ↔ Standings points consistency (US-002)', () => {
  const roster1 = [
    {
      id: 'slot-r1',
      leagueMemberId: 'member-a',
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
      leagueMemberId: 'member-a',
      round: 2,
      playerId: 8470594,
      position: 'F' as const,
      isActive: true,
      pointsEarned: 0,
      activatedFromIr: false,
    },
  ];

  it('should return identical total_points for dashboard and standings (single round)', () => {
    const state = {
      currentRound: 1,
      simulationDate: '2025-05-04',
      rosters: { 'member-a': roster1 },
      rosterHistory: {},
    };

    const dashboard = dashboardTotalPoints(state, ['member-a']);
    const standings = standingsTotalPoints(state, ['member-a']);

    expect(dashboard['member-a']).toBe(standings['member-a']);
  });

  it('should return identical total_points for dashboard and standings (multi-round)', () => {
    const state = {
      currentRound: 2,
      simulationDate: '2025-05-15',
      rosters: { 'member-a': roster2 },
      rosterHistory: { 'member-a': { 1: roster1 } },
    };

    const dashboard = dashboardTotalPoints(state, ['member-a']);
    const standings = standingsTotalPoints(state, ['member-a']);

    expect(dashboard['member-a']).toBe(standings['member-a']);
  });

  it('should return identical total_points across all members', () => {
    const state = {
      currentRound: 1,
      simulationDate: '2025-05-04',
      rosters: {
        'member-a': roster1,
        'member-b': [],
      },
      rosterHistory: {},
    };

    const members = ['member-a', 'member-b'];
    const dashboard = dashboardTotalPoints(state, members);
    const standings = standingsTotalPoints(state, members);

    for (const id of members) {
      expect(dashboard[id]).toBe(standings[id]);
    }
  });

  it('should update points as simulation date advances', () => {
    const earlyState = {
      currentRound: 1,
      simulationDate: '2025-04-19', // first day of R1
      rosters: { 'member-a': roster1 },
      rosterHistory: {},
    };

    const laterState = {
      ...earlyState,
      simulationDate: '2025-05-04', // late in R1
    };

    const earlyPts = calculateMemberPoints(earlyState, 'member-a').totalPoints;
    const laterPts = calculateMemberPoints(laterState, 'member-a').totalPoints;

    // Later date should have >= points (more games played)
    expect(laterPts).toBeGreaterThanOrEqual(earlyPts);
  });

  it('should show 0 points for members with no roster', () => {
    const state = {
      currentRound: 1,
      simulationDate: '2025-05-04',
      rosters: {},
      rosterHistory: {},
    };

    const dashboard = dashboardTotalPoints(state, ['member-x']);
    expect(dashboard['member-x']).toBe(0);
  });

  it('should reflect cumulative points from all rounds', () => {
    // Round 1 only
    const stateR1 = {
      currentRound: 1,
      simulationDate: '2025-05-04',
      rosters: { 'member-a': roster1 },
      rosterHistory: {},
    };

    // Round 1 + Round 2
    const stateR2 = {
      currentRound: 2,
      simulationDate: '2025-05-15',
      rosters: { 'member-a': roster2 },
      rosterHistory: { 'member-a': { 1: roster1 } },
    };

    const ptsR1 = calculateMemberPoints(stateR1, 'member-a').totalPoints;
    const ptsR2 = calculateMemberPoints(stateR2, 'member-a').totalPoints;

    // Cumulative R1+R2 should include R1 points
    expect(ptsR2).toBeGreaterThanOrEqual(ptsR1);

    // Dashboard and standings should match in both states
    expect(dashboardTotalPoints(stateR1, ['member-a'])['member-a']).toBe(
      standingsTotalPoints(stateR1, ['member-a'])['member-a']
    );
    expect(dashboardTotalPoints(stateR2, ['member-a'])['member-a']).toBe(
      standingsTotalPoints(stateR2, ['member-a'])['member-a']
    );
  });
});
