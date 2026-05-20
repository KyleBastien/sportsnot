import { describe, it, expect } from '@rstest/core';
import {
  buildPlayerTeamIdMap,
  computeAliveTeamIds,
  decorateSlotsWithElimination,
  isSlotEliminated,
  type EliminationMaps,
} from './eliminationUtils';

const r3Teams = [
  { team_id: 1, team_abbreviation: 'AAA', is_eliminated: false },
  { team_id: 2, team_abbreviation: 'BBB', is_eliminated: false },
  { team_id: 3, team_abbreviation: 'CCC', is_eliminated: false },
  { team_id: 4, team_abbreviation: 'DDD', is_eliminated: false },
];

const r4Teams = [
  { team_id: 1, team_abbreviation: 'AAA', is_eliminated: false },
  { team_id: 3, team_abbreviation: 'CCC', is_eliminated: false },
];

const r3Players = [
  { player_id: 100, team_abbreviation: 'AAA' },
  { player_id: 200, team_abbreviation: 'BBB' },
  { player_id: 300, team_abbreviation: 'CCC' },
  { player_id: 400, team_abbreviation: 'DDD' },
];

describe('computeAliveTeamIds', () => {
  it('uses next round cache when present and round < 4', () => {
    const result = computeAliveTeamIds({
      round: 3,
      currentRoundTeamStats: r3Teams,
      nextRoundTeamStats: r4Teams,
    });
    expect(result.hasEliminationData).toBe(true);
    expect([...result.aliveTeamIds].sort()).toEqual([1, 3]);
  });

  it('falls back to current round cache when next round empty (R<4)', () => {
    const result = computeAliveTeamIds({
      round: 3,
      currentRoundTeamStats: r3Teams,
      nextRoundTeamStats: [],
    });
    expect(result.hasEliminationData).toBe(true);
    expect([...result.aliveTeamIds].sort()).toEqual([1, 2, 3, 4]);
  });

  it('uses current round cache for R=4', () => {
    const result = computeAliveTeamIds({
      round: 4,
      currentRoundTeamStats: r4Teams,
      nextRoundTeamStats: [],
    });
    expect([...result.aliveTeamIds].sort()).toEqual([1, 3]);
  });

  it('honours explicit is_eliminated flag in fallback path', () => {
    const result = computeAliveTeamIds({
      round: 4,
      currentRoundTeamStats: [
        { team_id: 1, team_abbreviation: 'AAA', is_eliminated: false },
        { team_id: 3, team_abbreviation: 'CCC', is_eliminated: true },
      ],
      nextRoundTeamStats: [],
    });
    expect([...result.aliveTeamIds]).toEqual([1]);
  });

  it('reports no data when both caches empty', () => {
    const result = computeAliveTeamIds({
      round: 3,
      currentRoundTeamStats: [],
      nextRoundTeamStats: [],
    });
    expect(result.hasEliminationData).toBe(false);
    expect(result.aliveTeamIds.size).toBe(0);
  });
});

describe('buildPlayerTeamIdMap', () => {
  it('chains player abbr through team rows', () => {
    const map = buildPlayerTeamIdMap(r3Players, r3Teams);
    expect(map.get(100)).toBe(1);
    expect(map.get(200)).toBe(2);
    expect(map.get(400)).toBe(4);
  });

  it('accepts multiple team_stats sources', () => {
    const map = buildPlayerTeamIdMap(r3Players, r4Teams, r3Teams);
    expect(map.get(100)).toBe(1);
    expect(map.get(200)).toBe(2);
    expect(map.get(300)).toBe(3);
    expect(map.get(400)).toBe(4);
  });

  it('skips players with unknown abbreviation', () => {
    const map = buildPlayerTeamIdMap(
      [{ player_id: 999, team_abbreviation: 'ZZZ' }],
      r3Teams
    );
    expect(map.has(999)).toBe(false);
  });
});

describe('isSlotEliminated', () => {
  function makeMaps(): EliminationMaps {
    return {
      aliveTeamIds: new Set([1, 3]),
      playerTeamIdByPlayerId: buildPlayerTeamIdMap(r3Players, r3Teams),
      hasEliminationData: true,
    };
  }

  it('returns false when data not loaded', () => {
    expect(
      isSlotEliminated(
        { player_id: 200, team_id: null },
        {
          aliveTeamIds: new Set(),
          playerTeamIdByPlayerId: new Map(),
          hasEliminationData: false,
        }
      )
    ).toBe(false);
  });

  it('crosses out skater slot whose team is not alive', () => {
    const maps = makeMaps();
    expect(isSlotEliminated({ player_id: 200, team_id: null }, maps)).toBe(
      true
    );
    expect(isSlotEliminated({ player_id: 100, team_id: null }, maps)).toBe(
      false
    );
  });

  it('crosses out goalie/team slot whose team is not alive', () => {
    const maps = makeMaps();
    expect(isSlotEliminated({ player_id: null, team_id: 4 }, maps)).toBe(true);
    expect(isSlotEliminated({ player_id: null, team_id: 3 }, maps)).toBe(false);
  });

  it('returns false when slot has neither player nor team', () => {
    const maps = makeMaps();
    expect(isSlotEliminated({ player_id: null, team_id: null }, maps)).toBe(
      false
    );
  });

  it('returns false when player has no resolvable team mapping', () => {
    const maps = makeMaps();
    expect(isSlotEliminated({ player_id: 9999, team_id: null }, maps)).toBe(
      false
    );
  });
});

describe('decorateSlotsWithElimination', () => {
  it('sets is_eliminated on each slot', () => {
    const maps: EliminationMaps = {
      aliveTeamIds: new Set([1, 3]),
      playerTeamIdByPlayerId: buildPlayerTeamIdMap(r3Players, r3Teams),
      hasEliminationData: true,
    };
    const slots = [
      { id: 's1', player_id: 200, team_id: null },
      { id: 's2', player_id: 100, team_id: null },
      { id: 's3', player_id: null, team_id: 4 },
    ];
    const decorated = decorateSlotsWithElimination(slots, maps);
    expect(decorated.map((s) => s.is_eliminated)).toEqual([true, false, true]);
  });
});
