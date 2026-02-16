import { describe, it, expect } from '@rstest/core';
import {
  calculatePlayerPoints,
  calculateGoaliePoints,
  calculateGoalieGamePoints,
  generateSnakeDraftOrder,
  generateReDraftOrder,
  shuffleArray,
  generateInviteCode,
  buildPlayerNameMap,
  buildTeamNameMap,
  resolvePickName,
  aggregateStandingsPoints,
  aggregateRoundPoints,
  toggleColorScheme,
  resolveAutoColorScheme,
  archiveRostersForRoundAdvance,
  getRosterForRound,
} from './utils';
import type { PlayerStats, TeamStats } from '@sportsnot/types';

function makePlayerStats(overrides: Partial<PlayerStats>): PlayerStats {
  return {
    playerId: 1,
    nhlSeason: '20252026',
    playoffRound: 1,
    goals: 0,
    assists: 0,
    gamesPlayed: 0,
    isInjured: false,
    lastUpdated: new Date().toISOString(),
    ...overrides,
  };
}

function makeTeamStats(overrides: Partial<TeamStats>): TeamStats {
  return {
    teamId: 1,
    nhlSeason: '20252026',
    playoffRound: 1,
    wins: 0,
    shutouts: 0,
    isEliminated: false,
    lastUpdated: new Date().toISOString(),
    ...overrides,
  };
}

describe('calculatePlayerPoints', () => {
  it('should calculate points for goals and assists', () => {
    const stats = makePlayerStats({ goals: 3, assists: 5, gamesPlayed: 4 });
    expect(calculatePlayerPoints(stats)).toBe(8); // 3*1 + 5*1
  });

  it('should return 0 for no stats', () => {
    const stats = makePlayerStats({ goals: 0, assists: 0, gamesPlayed: 0 });
    expect(calculatePlayerPoints(stats)).toBe(0);
  });

  it('should handle high stat lines', () => {
    const stats = makePlayerStats({ goals: 14, assists: 18, gamesPlayed: 28 });
    expect(calculatePlayerPoints(stats)).toBe(32);
  });
});

describe('calculateGoaliePoints', () => {
  it('should calculate win points correctly', () => {
    const stats = makeTeamStats({ wins: 4, shutouts: 0 });
    expect(calculateGoaliePoints(stats)).toBe(8); // 4*2
  });

  it('should replace win points with shutout points', () => {
    const stats = makeTeamStats({ wins: 4, shutouts: 1 });
    // 3 regular wins * 2 + 1 shutout * 4 = 10
    expect(calculateGoaliePoints(stats)).toBe(10);
  });

  it('should handle all shutouts', () => {
    const stats = makeTeamStats({ wins: 4, shutouts: 4 });
    // 0 regular wins + 4 shutouts * 4 = 16
    expect(calculateGoaliePoints(stats)).toBe(16);
  });

  it('should return 0 for no wins', () => {
    const stats = makeTeamStats({ wins: 0, shutouts: 0 });
    expect(calculateGoaliePoints(stats)).toBe(0);
  });
});

describe('generateSnakeDraftOrder', () => {
  it('should generate correct snake order for 2 players, 2 rounds', () => {
    const order = generateSnakeDraftOrder(['A', 'B'], 2);
    expect(order).toEqual(['A', 'B', 'B', 'A']);
  });

  it('should generate correct snake order for 3 players, 3 rounds', () => {
    const order = generateSnakeDraftOrder(['A', 'B', 'C'], 3);
    expect(order).toEqual(['A', 'B', 'C', 'C', 'B', 'A', 'A', 'B', 'C']);
  });

  it('should return empty for 0 rounds', () => {
    const order = generateSnakeDraftOrder(['A', 'B'], 0);
    expect(order).toEqual([]);
  });

  it('should handle single player', () => {
    const order = generateSnakeDraftOrder(['A'], 3);
    expect(order).toEqual(['A', 'A', 'A']);
  });
});

describe('generateReDraftOrder', () => {
  it('should order worst to best (ascending points)', () => {
    const standings = [
      { memberId: 'A', points: 20 },
      { memberId: 'B', points: 5 },
      { memberId: 'C', points: 15 },
    ];
    const order = generateReDraftOrder(standings, 1);
    // Worst first: B(5), C(15), A(20)
    expect(order).toEqual(['B', 'C', 'A']);
  });

  it('should apply snake pattern for multiple rounds', () => {
    const standings = [
      { memberId: 'A', points: 10 },
      { memberId: 'B', points: 5 },
    ];
    const order = generateReDraftOrder(standings, 2);
    // Worst first: B, A → snake: B, A, A, B
    expect(order).toEqual(['B', 'A', 'A', 'B']);
  });
});

describe('shuffleArray', () => {
  it('should return array of same length', () => {
    const original = [1, 2, 3, 4, 5];
    const shuffled = shuffleArray(original);
    expect(shuffled.length).toBe(original.length);
  });

  it('should contain all original elements', () => {
    const original = [1, 2, 3, 4, 5];
    const shuffled = shuffleArray(original);
    expect(shuffled.sort()).toEqual(original.sort());
  });

  it('should not mutate the original array', () => {
    const original = [1, 2, 3, 4, 5];
    const copy = [...original];
    shuffleArray(original);
    expect(original).toEqual(copy);
  });

  it('should handle empty array', () => {
    expect(shuffleArray([])).toEqual([]);
  });

  it('should handle single element', () => {
    expect(shuffleArray([42])).toEqual([42]);
  });
});

describe('generateInviteCode', () => {
  it('should generate an 8-character code', () => {
    const code = generateInviteCode();
    expect(code.length).toBe(8);
  });

  it('should only contain valid characters', () => {
    const validChars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    const code = generateInviteCode();
    for (const char of code) {
      expect(validChars).toContain(char);
    }
  });

  it('should generate unique codes', () => {
    const codes = new Set<string>();
    for (let i = 0; i < 100; i++) {
      codes.add(generateInviteCode());
    }
    // With 31^8 possible codes, 100 codes should all be unique
    expect(codes.size).toBe(100);
  });
});

describe('buildPlayerNameMap', () => {
  it('should build a map from player stat rows', () => {
    const players = [
      { player_id: 8478402, player_name: 'Connor McDavid' },
      { player_id: 8477934, player_name: 'Leon Draisaitl' },
    ];
    const map = buildPlayerNameMap(players);
    expect(map.get(8478402)).toBe('Connor McDavid');
    expect(map.get(8477934)).toBe('Leon Draisaitl');
    expect(map.size).toBe(2);
  });

  it('should skip entries with null or undefined player_name', () => {
    const players = [
      { player_id: 1, player_name: 'Valid Player' },
      { player_id: 2, player_name: null },
      { player_id: 3, player_name: undefined },
    ];
    const map = buildPlayerNameMap(players);
    expect(map.size).toBe(1);
    expect(map.get(1)).toBe('Valid Player');
    expect(map.has(2)).toBe(false);
  });

  it('should handle empty array', () => {
    const map = buildPlayerNameMap([]);
    expect(map.size).toBe(0);
  });
});

describe('buildTeamNameMap', () => {
  it('should build a map from team stat rows', () => {
    const teams = [
      { team_id: 22, team_name: 'Edmonton Oilers' },
      { team_id: 25, team_name: 'Dallas Stars' },
    ];
    const map = buildTeamNameMap(teams);
    expect(map.get(22)).toBe('Edmonton Oilers');
    expect(map.get(25)).toBe('Dallas Stars');
    expect(map.size).toBe(2);
  });

  it('should skip entries with null or undefined team_name', () => {
    const teams = [
      { team_id: 1, team_name: 'Valid Team' },
      { team_id: 2, team_name: null },
      { team_id: 3, team_name: undefined },
    ];
    const map = buildTeamNameMap(teams);
    expect(map.size).toBe(1);
    expect(map.get(1)).toBe('Valid Team');
  });

  it('should handle empty array', () => {
    const map = buildTeamNameMap([]);
    expect(map.size).toBe(0);
  });
});

describe('resolvePickName', () => {
  const playerMap = new Map([
    [8478402, 'Connor McDavid'],
    [8477934, 'Leon Draisaitl'],
  ]);
  const teamMap = new Map([
    [22, 'Edmonton Oilers'],
    [25, 'Dallas Stars'],
  ]);

  it('should resolve player_id to player name', () => {
    expect(resolvePickName(8478402, null, playerMap, teamMap)).toBe(
      'Connor McDavid'
    );
  });

  it('should resolve team_id when player_id is null', () => {
    expect(resolvePickName(null, 22, playerMap, teamMap)).toBe(
      'Edmonton Oilers'
    );
  });

  it('should return fallback for unknown player_id', () => {
    expect(resolvePickName(99999, null, playerMap, teamMap)).toBe(
      'Unknown Player'
    );
  });

  it('should return "Unknown Team" for unknown team_id', () => {
    expect(resolvePickName(null, 99999, playerMap, teamMap)).toBe(
      'Unknown Team'
    );
  });

  it('should return fallback when both IDs are null', () => {
    expect(resolvePickName(null, null, playerMap, teamMap)).toBe(
      'Unknown Player'
    );
  });

  it('should use custom fallback string', () => {
    expect(resolvePickName(null, null, playerMap, teamMap, 'N/A')).toBe('N/A');
  });

  it('should prefer player_id over team_id when both are present', () => {
    expect(resolvePickName(8478402, 22, playerMap, teamMap)).toBe(
      'Connor McDavid'
    );
  });
});

describe('Roster page name resolution', () => {
  const playerMap = new Map([
    [8478402, 'Connor McDavid'],
    [8477934, 'Leon Draisaitl'],
    [8476917, 'Zach Hyman'],
  ]);
  const teamMap = new Map([
    [22, 'Edmonton Oilers'],
    [25, 'Dallas Stars'],
  ]);

  it('should resolve Forward roster slots to player names', () => {
    const forwardSlots = [
      { player_id: 8478402, team_id: null, position: 'F' },
      { player_id: 8477934, team_id: null, position: 'F' },
      { player_id: 8476917, team_id: null, position: 'F' },
    ];
    const names = forwardSlots.map((s) =>
      resolvePickName(s.player_id, s.team_id, playerMap, teamMap)
    );
    expect(names).toEqual(['Connor McDavid', 'Leon Draisaitl', 'Zach Hyman']);
  });

  it('should resolve Goalie roster slots to team names', () => {
    const goalieSlots = [
      { player_id: null, team_id: 22, position: 'G' },
      { player_id: null, team_id: 25, position: 'G' },
    ];
    const names = goalieSlots.map((s) =>
      resolvePickName(s.player_id, s.team_id, playerMap, teamMap)
    );
    expect(names).toEqual(['Edmonton Oilers', 'Dallas Stars']);
  });

  it('should resolve IR roster slots the same as active slots', () => {
    const irSlots = [
      { player_id: 8476917, team_id: null, position: 'IR_F' },
      { player_id: 8477934, team_id: null, position: 'IR_D' },
    ];
    const names = irSlots.map((s) =>
      resolvePickName(s.player_id, s.team_id, playerMap, teamMap)
    );
    expect(names).toEqual(['Zach Hyman', 'Leon Draisaitl']);
  });

  it('should show fallback for unknown player IDs on roster', () => {
    const slot = { player_id: 99999, team_id: null, position: 'F' };
    expect(
      resolvePickName(slot.player_id, slot.team_id, playerMap, teamMap)
    ).toBe('Unknown Player');
  });

  it('should show fallback for unknown team IDs on roster', () => {
    const slot = { player_id: null, team_id: 99999, position: 'G' };
    expect(
      resolvePickName(slot.player_id, slot.team_id, playerMap, teamMap)
    ).toBe('Unknown Team');
  });

  it('should resolve a full mixed roster with players and teams', () => {
    const roster = [
      { player_id: 8478402, team_id: null, position: 'F', points_earned: 12 },
      { player_id: 8477934, team_id: null, position: 'F', points_earned: 8 },
      { player_id: 8476917, team_id: null, position: 'D', points_earned: 3 },
      { player_id: null, team_id: 22, position: 'G', points_earned: 6 },
      { player_id: 8476917, team_id: null, position: 'IR_F', points_earned: 0 },
    ];
    const names = roster.map((s) =>
      resolvePickName(s.player_id, s.team_id, playerMap, teamMap)
    );
    expect(names).toEqual([
      'Connor McDavid',
      'Leon Draisaitl',
      'Zach Hyman',
      'Edmonton Oilers',
      'Zach Hyman',
    ]);
    // Points should still be accessible alongside resolved names
    expect(roster.map((s) => s.points_earned)).toEqual([12, 8, 3, 6, 0]);
  });
});

describe('Draft Complete screen logic', () => {
  const playerMap = new Map([
    [8478402, 'Connor McDavid'],
    [8477934, 'Leon Draisaitl'],
    [8479318, 'Auston Matthews'],
  ]);
  const teamMap = new Map([
    [22, 'Edmonton Oilers'],
    [25, 'Dallas Stars'],
    [10, 'Toronto Maple Leafs'],
  ]);

  it('should resolve all picks in a draft results list', () => {
    const picks = [
      { player_id: 8478402, team_id: null, position: 'C' },
      { player_id: 8477934, team_id: null, position: 'LW' },
      { player_id: null, team_id: 22, position: 'G' },
      { player_id: 8479318, team_id: null, position: 'C' },
      { player_id: null, team_id: 25, position: 'G' },
    ];

    const resolved = picks.map((p) =>
      resolvePickName(p.player_id, p.team_id, playerMap, teamMap)
    );

    expect(resolved).toEqual([
      'Connor McDavid',
      'Leon Draisaitl',
      'Edmonton Oilers',
      'Auston Matthews',
      'Dallas Stars',
    ]);
  });

  it('should display team name for goalie picks (team_id only)', () => {
    expect(resolvePickName(null, 22, playerMap, teamMap)).toBe(
      'Edmonton Oilers'
    );
    expect(resolvePickName(null, 10, playerMap, teamMap)).toBe(
      'Toronto Maple Leafs'
    );
  });

  it('should construct correct Back to League URL from leagueId', () => {
    const leagueId = 'abc-123-def';
    const url = `/leagues/${leagueId}`;
    expect(url).toBe('/leagues/abc-123-def');
  });

  it('should handle draft with only goalie/team picks', () => {
    const picks = [
      { player_id: null, team_id: 22, position: 'G' },
      { player_id: null, team_id: 25, position: 'G' },
    ];
    const resolved = picks.map((p) =>
      resolvePickName(p.player_id, p.team_id, playerMap, teamMap)
    );
    expect(resolved).toEqual(['Edmonton Oilers', 'Dallas Stars']);
  });

  it('should handle draft with unknown player and team IDs gracefully', () => {
    const picks = [
      { player_id: 999, team_id: null, position: 'C' },
      { player_id: null, team_id: 999, position: 'G' },
    ];
    const resolved = picks.map((p) =>
      resolvePickName(p.player_id, p.team_id, playerMap, teamMap)
    );
    expect(resolved).toEqual(['Unknown Player', 'Unknown Team']);
  });
});

describe('calculateGoalieGamePoints', () => {
  it('should return 2 points for a regular win', () => {
    expect(calculateGoalieGamePoints(3, 1)).toBe(2);
  });

  it('should return 4 points for a shutout (opponent scores 0)', () => {
    expect(calculateGoalieGamePoints(2, 0)).toBe(4);
  });

  it('should return 0 for a loss', () => {
    expect(calculateGoalieGamePoints(1, 3)).toBe(0);
  });

  it('should return 0 for a tie', () => {
    expect(calculateGoalieGamePoints(2, 2)).toBe(0);
  });

  it('should not be additive: shutout replaces win (4 not 6)', () => {
    // A shutout is 4 points, not 4 + 2
    expect(calculateGoalieGamePoints(3, 0)).toBe(4);
  });

  it('should award 2 points for a 1-goal win margin', () => {
    expect(calculateGoalieGamePoints(2, 1)).toBe(2);
  });

  it('should correctly tally multiple games for a team', () => {
    // Simulate a team with 4 wins (3 regular + 1 shutout) and 3 losses
    const games = [
      { teamScore: 3, oppScore: 1 }, // win: 2pts
      { teamScore: 4, oppScore: 2 }, // win: 2pts
      { teamScore: 1, oppScore: 3 }, // loss: 0pts
      { teamScore: 2, oppScore: 0 }, // shutout: 4pts
      { teamScore: 5, oppScore: 3 }, // win: 2pts
      { teamScore: 0, oppScore: 2 }, // loss: 0pts
      { teamScore: 1, oppScore: 4 }, // loss: 0pts
    ];
    const totalPoints = games.reduce(
      (sum, g) => sum + calculateGoalieGamePoints(g.teamScore, g.oppScore),
      0
    );
    // 3 regular wins * 2 + 1 shutout * 4 = 10
    expect(totalPoints).toBe(10);
  });

  it('Oilers scenario: 4 wins with 0 shutouts = 8 goalie points', () => {
    const games = [
      { teamScore: 3, oppScore: 2 }, // win: 2pts
      { teamScore: 4, oppScore: 1 }, // win: 2pts
      { teamScore: 2, oppScore: 1 }, // win: 2pts
      { teamScore: 5, oppScore: 3 }, // win: 2pts
    ];
    const totalPoints = games.reduce(
      (sum, g) => sum + calculateGoalieGamePoints(g.teamScore, g.oppScore),
      0
    );
    expect(totalPoints).toBe(8);
  });
});

describe('aggregateStandingsPoints', () => {
  it('should separate player and goalie points', () => {
    const roster = [
      {
        player_id: 100,
        team_id: null,
        position: 'F',
        is_active: true,
        points_earned: 5,
      },
      {
        player_id: 101,
        team_id: null,
        position: 'D',
        is_active: true,
        points_earned: 3,
      },
      {
        player_id: null,
        team_id: 22,
        position: 'G',
        is_active: true,
        points_earned: 8,
      },
    ];
    const result = aggregateStandingsPoints(roster);
    expect(result.playerPts).toBe(8);
    expect(result.goaliePts).toBe(8);
    expect(result.total).toBe(16);
  });

  it('should exclude inactive slots', () => {
    const roster = [
      {
        player_id: 100,
        team_id: null,
        position: 'F',
        is_active: true,
        points_earned: 5,
      },
      {
        player_id: 101,
        team_id: null,
        position: 'D',
        is_active: false,
        points_earned: 10,
      },
      {
        player_id: null,
        team_id: 22,
        position: 'G',
        is_active: true,
        points_earned: 4,
      },
    ];
    const result = aggregateStandingsPoints(roster);
    expect(result.playerPts).toBe(5);
    expect(result.goaliePts).toBe(4);
    expect(result.total).toBe(9);
  });

  it('should return zeros for empty roster', () => {
    const result = aggregateStandingsPoints([]);
    expect(result.total).toBe(0);
    expect(result.playerPts).toBe(0);
    expect(result.goaliePts).toBe(0);
  });

  it('should handle roster with only goalie slots', () => {
    const roster = [
      {
        player_id: null,
        team_id: 22,
        position: 'G',
        is_active: true,
        points_earned: 6,
      },
    ];
    const result = aggregateStandingsPoints(roster);
    expect(result.playerPts).toBe(0);
    expect(result.goaliePts).toBe(6);
    expect(result.total).toBe(6);
  });

  it('should handle roster with only player slots', () => {
    const roster = [
      {
        player_id: 100,
        team_id: null,
        position: 'F',
        is_active: true,
        points_earned: 12,
      },
      {
        player_id: 101,
        team_id: null,
        position: 'D',
        is_active: true,
        points_earned: 4,
      },
    ];
    const result = aggregateStandingsPoints(roster);
    expect(result.playerPts).toBe(16);
    expect(result.goaliePts).toBe(0);
    expect(result.total).toBe(16);
  });

  it('total should always equal playerPts + goaliePts', () => {
    const roster = [
      {
        player_id: 100,
        team_id: null,
        position: 'F',
        is_active: true,
        points_earned: 7,
      },
      {
        player_id: 101,
        team_id: null,
        position: 'F',
        is_active: true,
        points_earned: 3,
      },
      {
        player_id: 102,
        team_id: null,
        position: 'D',
        is_active: true,
        points_earned: 2,
      },
      {
        player_id: null,
        team_id: 22,
        position: 'G',
        is_active: true,
        points_earned: 8,
      },
      {
        player_id: 103,
        team_id: null,
        position: 'IR_F',
        is_active: false,
        points_earned: 0,
      },
    ];
    const result = aggregateStandingsPoints(roster);
    expect(result.total).toBe(result.playerPts + result.goaliePts);
    expect(result.total).toBe(20);
  });
});

describe('aggregateRoundPoints', () => {
  it('should group points by round', () => {
    const roster = [
      {
        player_id: 100,
        position: 'F',
        is_active: true,
        points_earned: 5,
        round: 1,
      },
      {
        player_id: 101,
        position: 'D',
        is_active: true,
        points_earned: 3,
        round: 1,
      },
      {
        player_id: 102,
        position: 'F',
        is_active: true,
        points_earned: 7,
        round: 2,
      },
    ];
    const result = aggregateRoundPoints(roster);
    expect(result[1]).toBe(8);
    expect(result[2]).toBe(7);
  });

  it('should exclude inactive slots', () => {
    const roster = [
      {
        player_id: 100,
        position: 'F',
        is_active: true,
        points_earned: 5,
        round: 1,
      },
      {
        player_id: 101,
        position: 'D',
        is_active: false,
        points_earned: 10,
        round: 1,
      },
    ];
    const result = aggregateRoundPoints(roster);
    expect(result[1]).toBe(5);
  });

  it('should return empty object for empty roster', () => {
    const result = aggregateRoundPoints([]);
    expect(Object.keys(result).length).toBe(0);
  });

  it('should handle four rounds', () => {
    const roster = [
      {
        player_id: 100,
        position: 'F',
        is_active: true,
        points_earned: 5,
        round: 1,
      },
      {
        player_id: 100,
        position: 'F',
        is_active: true,
        points_earned: 3,
        round: 2,
      },
      {
        player_id: 100,
        position: 'F',
        is_active: true,
        points_earned: 8,
        round: 3,
      },
      {
        player_id: 100,
        position: 'F',
        is_active: true,
        points_earned: 2,
        round: 4,
      },
    ];
    const result = aggregateRoundPoints(roster);
    expect(result[1]).toBe(5);
    expect(result[2]).toBe(3);
    expect(result[3]).toBe(8);
    expect(result[4]).toBe(2);
  });
});

// ── Dark-mode / color scheme utilities ──────────────────────────────

describe('toggleColorScheme', () => {
  it('returns dark when current is light', () => {
    expect(toggleColorScheme('light')).toBe('dark');
  });

  it('returns light when current is dark', () => {
    expect(toggleColorScheme('dark')).toBe('light');
  });

  it('is its own inverse', () => {
    expect(toggleColorScheme(toggleColorScheme('light'))).toBe('light');
    expect(toggleColorScheme(toggleColorScheme('dark'))).toBe('dark');
  });
});

describe('resolveAutoColorScheme', () => {
  it('returns dark when user prefers dark', () => {
    expect(resolveAutoColorScheme(true)).toBe('dark');
  });

  it('returns light when user does not prefer dark', () => {
    expect(resolveAutoColorScheme(false)).toBe('light');
  });
});

// ── Roster round-transition utilities ──────────────────────────────

describe('archiveRostersForRoundAdvance', () => {
  const makeSlot = (memberId: string, round: number, id: string) => ({
    id,
    leagueMemberId: memberId,
    round,
    playerId: 100,
    position: 'F' as const,
    isActive: true,
    pointsEarned: 5,
    activatedFromIr: false,
  });

  it('should archive current rosters and return empty cleared rosters', () => {
    const currentRosters = {
      member1: [makeSlot('member1', 1, 'slot-1')],
      member2: [makeSlot('member2', 1, 'slot-2')],
    };
    const result = archiveRostersForRoundAdvance(currentRosters, {}, 1);
    expect(result.clearedRosters).toEqual({});
    expect(result.rosterHistory['member1'][1]).toEqual(
      currentRosters['member1']
    );
    expect(result.rosterHistory['member2'][1]).toEqual(
      currentRosters['member2']
    );
  });

  it('should preserve existing history when archiving new round', () => {
    const r1Slots = [makeSlot('member1', 1, 'slot-r1')];
    const r2Slots = [makeSlot('member1', 2, 'slot-r2')];
    const existingHistory = { member1: { 1: r1Slots } };
    const result = archiveRostersForRoundAdvance(
      { member1: r2Slots },
      existingHistory,
      2
    );
    expect(result.rosterHistory['member1'][1]).toEqual(r1Slots);
    expect(result.rosterHistory['member1'][2]).toEqual(r2Slots);
  });

  it('should handle empty current rosters', () => {
    const result = archiveRostersForRoundAdvance({}, {}, 1);
    expect(result.clearedRosters).toEqual({});
    expect(result.rosterHistory).toEqual({});
  });

  it('should handle multiple members across rounds', () => {
    const history = {
      member1: { 1: [makeSlot('member1', 1, 's1')] },
      member2: { 1: [makeSlot('member2', 1, 's2')] },
    };
    const current = {
      member1: [makeSlot('member1', 2, 's3')],
      member2: [makeSlot('member2', 2, 's4')],
      member3: [makeSlot('member3', 2, 's5')],
    };
    const result = archiveRostersForRoundAdvance(current, history, 2);
    expect(Object.keys(result.rosterHistory)).toEqual([
      'member1',
      'member2',
      'member3',
    ]);
    expect(result.rosterHistory['member1'][1]).toBeDefined();
    expect(result.rosterHistory['member1'][2]).toBeDefined();
    expect(result.rosterHistory['member3'][2]).toBeDefined();
  });
});

describe('getRosterForRound', () => {
  const makeSlot = (round: number, id: string) => ({
    id,
    round,
    playerId: 100,
  });

  it('should return current rosters for the current round', () => {
    const current = { member1: [makeSlot(2, 'current-slot')] };
    const history = { member1: { 1: [makeSlot(1, 'hist-slot')] } };
    const result = getRosterForRound('member1', 2, 2, current, history);
    expect(result).toEqual([makeSlot(2, 'current-slot')]);
  });

  it('should return historical rosters for past rounds', () => {
    const current = { member1: [makeSlot(2, 'current-slot')] };
    const history = { member1: { 1: [makeSlot(1, 'hist-slot')] } };
    const result = getRosterForRound('member1', 1, 2, current, history);
    expect(result).toEqual([makeSlot(1, 'hist-slot')]);
  });

  it('should return empty array when no roster exists for round', () => {
    const result = getRosterForRound('member1', 3, 3, {}, {});
    expect(result).toEqual([]);
  });

  it('should return empty array for unknown member', () => {
    const current = { member1: [makeSlot(1, 's1')] };
    const result = getRosterForRound('unknown', 1, 1, current, {});
    expect(result).toEqual([]);
  });

  it('should return empty array for current round with cleared rosters', () => {
    const history = { member1: { 1: [makeSlot(1, 'hist')] } };
    const result = getRosterForRound('member1', 2, 2, {}, history);
    expect(result).toEqual([]);
  });
});

// ── Re-draft order and commissioner logic tests ─────────────────────

describe('Re-draft order (generateReDraftOrder)', () => {
  it('should order worst-to-best by points for first round of snake', () => {
    const standings = [
      { memberId: 'alpha', points: 25 },
      { memberId: 'beta', points: 40 },
      { memberId: 'gamma', points: 15 },
      { memberId: 'delta', points: 32 },
    ];
    const order = generateReDraftOrder(standings, 1);
    // Sorted worst first: gamma(15), alpha(25), delta(32), beta(40)
    expect(order).toEqual(['gamma', 'alpha', 'delta', 'beta']);
  });

  it('should generate snake pattern with reversed second round', () => {
    const standings = [
      { memberId: 'a', points: 10 },
      { memberId: 'b', points: 20 },
      { memberId: 'c', points: 30 },
    ];
    const order = generateReDraftOrder(standings, 2);
    // Round 1: a, b, c (worst to best)
    // Round 2: c, b, a (reversed)
    expect(order).toEqual(['a', 'b', 'c', 'c', 'b', 'a']);
  });

  it('should handle tied points (stable sort)', () => {
    const standings = [
      { memberId: 'x', points: 20 },
      { memberId: 'y', points: 20 },
    ];
    const order = generateReDraftOrder(standings, 1);
    expect(order).toHaveLength(2);
    expect(order).toContain('x');
    expect(order).toContain('y');
  });

  it('should handle single member', () => {
    const standings = [{ memberId: 'solo', points: 100 }];
    const order = generateReDraftOrder(standings, 3);
    expect(order).toEqual(['solo', 'solo', 'solo']);
  });

  it('should generate full 11-round snake draft order', () => {
    const standings = [
      { memberId: 'a', points: 5 },
      { memberId: 'b', points: 10 },
    ];
    const order = generateReDraftOrder(standings, 11);
    // 11 rounds × 2 members = 22 total picks
    expect(order).toHaveLength(22);
    // Odd rounds (0,2,4,...): a,b — Even rounds (1,3,5,...): b,a
    expect(order[0]).toBe('a'); // Round 1: worst first
    expect(order[1]).toBe('b');
    expect(order[2]).toBe('b'); // Round 2: reversed
    expect(order[3]).toBe('a');
  });

  it('should give worst team first pick overall', () => {
    const standings = [
      { memberId: 'best', points: 100 },
      { memberId: 'mid', points: 50 },
      { memberId: 'worst', points: 0 },
    ];
    const order = generateReDraftOrder(standings, 1);
    expect(order[0]).toBe('worst');
    expect(order[2]).toBe('best');
  });
});
