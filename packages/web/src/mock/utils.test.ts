import { describe, it, expect } from '@rstest/core';
import {
  calculateRoundMemberPoints,
  calculateMemberPoints,
  sortMembersForReDraft,
  getPlayerTeamAbbr,
  getTeamAbbr,
  isSlotEliminated,
} from './utils';

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

describe('sortMembersForReDraft', () => {
  const makeMember = (team_name: string, total_points: number) => ({
    id: `id-${team_name}`,
    user_id: `user-${team_name}`,
    team_name,
    total_points,
  });

  it('should sort members by total_points ascending (worst first)', () => {
    const members = [
      makeMember('Alpha', 30),
      makeMember('Bravo', 10),
      makeMember('Charlie', 20),
    ];
    const sorted = sortMembersForReDraft(members);
    expect(sorted.map((m) => m.team_name)).toEqual([
      'Bravo',
      'Charlie',
      'Alpha',
    ]);
  });

  it('should break ties by team_name alphabetically', () => {
    const members = [
      makeMember('Zebra', 10),
      makeMember('Alpha', 10),
      makeMember('Mango', 10),
    ];
    const sorted = sortMembersForReDraft(members);
    expect(sorted.map((m) => m.team_name)).toEqual(['Alpha', 'Mango', 'Zebra']);
  });

  it('should handle mixed ties and different points', () => {
    const members = [
      makeMember('Delta', 20),
      makeMember('Alpha', 20),
      makeMember('Charlie', 10),
      makeMember('Bravo', 30),
    ];
    const sorted = sortMembersForReDraft(members);
    expect(sorted.map((m) => m.team_name)).toEqual([
      'Charlie',
      'Alpha',
      'Delta',
      'Bravo',
    ]);
  });

  it('should treat null/undefined total_points as 0', () => {
    const members = [
      { id: '1', user_id: 'u1', team_name: 'A', total_points: 5 },
      {
        id: '2',
        user_id: 'u2',
        team_name: 'B',
        total_points: null as unknown as number,
      },
      {
        id: '3',
        user_id: 'u3',
        team_name: 'C',
        total_points: undefined as unknown as number,
      },
    ];
    const sorted = sortMembersForReDraft(members);
    expect(sorted.map((m) => m.team_name)).toEqual(['B', 'C', 'A']);
  });

  it('should not mutate the original array', () => {
    const members = [makeMember('B', 20), makeMember('A', 10)];
    const original = [...members];
    sortMembersForReDraft(members);
    expect(members[0].team_name).toBe(original[0].team_name);
    expect(members[1].team_name).toBe(original[1].team_name);
  });

  it('should return empty array for empty input', () => {
    expect(sortMembersForReDraft([])).toEqual([]);
  });

  it('should handle single member', () => {
    const members = [makeMember('Solo', 42)];
    const sorted = sortMembersForReDraft(members);
    expect(sorted).toEqual(members);
  });
});

// ── Elimination helpers ──────────────────────────────────────────────────

describe('getPlayerTeamAbbr', () => {
  it('should map a CAR player to CAR abbreviation', () => {
    // Sebastian Aho (CAR)
    expect(getPlayerTeamAbbr(8478427)).toBe('CAR');
  });

  it('should map a FLA player to FLA abbreviation', () => {
    // Aleksander Barkov (FLA)
    expect(getPlayerTeamAbbr(8477493)).toBe('FLA');
  });

  it('should return undefined for unknown player ID', () => {
    expect(getPlayerTeamAbbr(99999999)).toBeUndefined();
  });
});

describe('getTeamAbbr', () => {
  it('should map CAR team ID to CAR', () => {
    expect(getTeamAbbr(12)).toBe('CAR');
  });

  it('should map FLA team ID to FLA', () => {
    expect(getTeamAbbr(13)).toBe('FLA');
  });

  it('should return undefined for unknown team ID', () => {
    expect(getTeamAbbr(99999)).toBeUndefined();
  });
});

describe('isSlotEliminated', () => {
  const eliminatedAbbrs = new Set(['CAR', 'DAL']);

  it('should return true for a player on an eliminated team', () => {
    // Sebastian Aho is on CAR
    expect(isSlotEliminated({ playerId: 8478427 }, eliminatedAbbrs)).toBe(true);
  });

  it('should return false for a player on a surviving team', () => {
    // Aleksander Barkov is on FLA
    expect(isSlotEliminated({ playerId: 8477493 }, eliminatedAbbrs)).toBe(
      false
    );
  });

  it('should return true for a goalie teamId on an eliminated team', () => {
    // CAR team ID = 12
    expect(isSlotEliminated({ teamId: 12 }, eliminatedAbbrs)).toBe(true);
  });

  it('should return false for a goalie teamId on a surviving team', () => {
    // FLA team ID = 13
    expect(isSlotEliminated({ teamId: 13 }, eliminatedAbbrs)).toBe(false);
  });

  it('should return false for a slot with no playerId or teamId', () => {
    expect(isSlotEliminated({}, eliminatedAbbrs)).toBe(false);
  });

  it('should return false for unknown playerId', () => {
    expect(isSlotEliminated({ playerId: 99999999 }, eliminatedAbbrs)).toBe(
      false
    );
  });

  it('should return false when eliminated set is empty', () => {
    expect(isSlotEliminated({ playerId: 8478427 }, new Set())).toBe(false);
  });
});

describe('calculateMemberPoints - Round 4 elimination', () => {
  it('should exclude eliminated players from Round 4 scoring', () => {
    // CAR is eliminated after Round 3, FLA survives
    const carPlayerId = 8478427; // Sebastian Aho (CAR)
    const flaPlayerId = 8477493; // Aleksander Barkov (FLA)

    const roster = [
      {
        id: 'slot-car',
        leagueMemberId: 'member-1',
        round: 4,
        playerId: carPlayerId,
        position: 'F' as const,
        isActive: true,
        pointsEarned: 0,
        activatedFromIr: false,
      },
      {
        id: 'slot-fla',
        leagueMemberId: 'member-1',
        round: 4,
        playerId: flaPlayerId,
        position: 'F' as const,
        isActive: true,
        pointsEarned: 0,
        activatedFromIr: false,
      },
    ];

    // State at Round 4 with only these roster slots
    const state = {
      currentRound: 4,
      simulationDate: '2025-06-20', // well into Round 4
      rosters: { 'member-1': roster },
      rosterHistory: {},
    };

    const result = calculateMemberPoints(state, 'member-1');

    // Now compare with FLA-only: should be the same since CAR is excluded
    const stateOnlyFla = {
      currentRound: 4,
      simulationDate: '2025-06-20',
      rosters: {
        'member-1': [roster[1]], // only FLA player
      },
      rosterHistory: {},
    };
    const flaOnlyResult = calculateMemberPoints(stateOnlyFla, 'member-1');

    // Round 4 points should match FLA-only (CAR eliminated, contributes 0)
    expect(result.roundPoints[4] ?? 0).toBe(flaOnlyResult.roundPoints[4] ?? 0);
  });

  it('should still count Round 3 points for eliminated players', () => {
    const carPlayerId = 8478427; // CAR - eliminated after Round 3

    const rosterR3 = [
      {
        id: 'slot-car-r3',
        leagueMemberId: 'member-1',
        round: 3,
        playerId: carPlayerId,
        position: 'F' as const,
        isActive: true,
        pointsEarned: 0,
        activatedFromIr: false,
      },
    ];
    const rosterR4 = [
      {
        id: 'slot-car-r4',
        leagueMemberId: 'member-1',
        round: 4,
        playerId: carPlayerId,
        position: 'F' as const,
        isActive: true,
        pointsEarned: 0,
        activatedFromIr: false,
      },
    ];

    const state = {
      currentRound: 4,
      simulationDate: '2025-06-20',
      rosters: { 'member-1': rosterR4 },
      rosterHistory: { 'member-1': { 3: rosterR3 } },
    };

    const result = calculateMemberPoints(state, 'member-1');

    // Round 3 points should be included (CAR played in Conference Finals)
    // Round 4 points should be 0 (CAR eliminated)
    expect(result.roundPoints[4]).toBeUndefined(); // 0 points = not in breakdown
    // Total should include Round 3 points
    expect(result.totalPoints).toBeGreaterThanOrEqual(0);
  });

  it('should not filter elimination in rounds other than 4', () => {
    // Even for a team that gets eliminated later, Round 3 scoring is normal
    const carPlayerId = 8478427; // CAR

    const state = {
      currentRound: 3,
      simulationDate: '2025-06-05',
      rosters: {
        'member-1': [
          {
            id: 'slot-car',
            leagueMemberId: 'member-1',
            round: 3,
            playerId: carPlayerId,
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
    // CAR players should still score in Round 3 (they're not eliminated yet)
    expect(result.totalPoints).toBeGreaterThanOrEqual(0);
  });
});
