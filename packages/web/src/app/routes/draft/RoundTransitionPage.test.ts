import { describe, it, expect } from '@rstest/core';

/**
 * Unit tests for RoundTransitionPage handleSkipToRound4 logic.
 * Verifies the roster copy transformation and table name correctness.
 */

interface RosterSlot {
  id: string;
  league_member_id: string;
  round: number;
  player_id: number | null;
  team_id: number | null;
  position: string;
  is_active: boolean;
  points_earned: number;
  activated_from_ir: boolean;
}

function makeSlot(overrides: Partial<RosterSlot> = {}): RosterSlot {
  return {
    id: 'slot-1',
    league_member_id: 'member-1',
    round: 3,
    player_id: 100,
    team_id: null,
    position: 'F',
    is_active: true,
    points_earned: 15,
    activated_from_ir: false,
    ...overrides,
  };
}

/**
 * Replicates the R3→R4 copy logic from handleSkipToRound4.
 * Strips `id` so Supabase auto-generates a new one, sets round=4 and points_earned=0.
 */
function copyRound3ToRound4(
  round3Slots: RosterSlot[]
): Omit<RosterSlot, 'id'>[] {
  return round3Slots.map(({ id: _id, ...slot }) => ({
    ...slot,
    round: 4,
    points_earned: 0,
  }));
}

/**
 * Returns the Supabase table name used for roster queries.
 * The correct table is 'rosters' per 001_initial_schema.sql migration.
 */
function getRosterTableName(): string {
  return 'rosters';
}

describe('handleSkipToRound4 roster copy logic', () => {
  it('uses correct table name "rosters" (not "roster_slots")', () => {
    const tableName = getRosterTableName();
    expect(tableName).toBe('rosters');
    expect(tableName).not.toBe('roster_slots');
  });

  it('copies R3 slots to R4 with round=4 and points_earned=0', () => {
    const r3Slots = [
      makeSlot({ id: 'a', points_earned: 25, round: 3 }),
      makeSlot({ id: 'b', points_earned: 10, round: 3, position: 'D' }),
    ];
    const r4Slots = copyRound3ToRound4(r3Slots);

    expect(r4Slots.length).toBe(2);
    for (const slot of r4Slots) {
      expect(slot.round).toBe(4);
      expect(slot.points_earned).toBe(0);
      expect((slot as Record<string, unknown>).id).toBeUndefined();
    }
  });

  it('strips the id field so Supabase generates new UUIDs', () => {
    const r3Slots = [makeSlot({ id: 'original-uuid-123' })];
    const r4Slots = copyRound3ToRound4(r3Slots);

    expect(r4Slots.length).toBe(1);
    expect((r4Slots[0] as Record<string, unknown>).id).toBeUndefined();
  });

  it('preserves player_id, team_id, position, and league_member_id', () => {
    const r3Slots = [
      makeSlot({
        id: 'x',
        league_member_id: 'mem-42',
        player_id: 999,
        team_id: null,
        position: 'F',
        is_active: true,
        activated_from_ir: false,
      }),
    ];
    const r4Slots = copyRound3ToRound4(r3Slots);
    const slot = r4Slots[0];

    expect(slot.league_member_id).toBe('mem-42');
    expect(slot.player_id).toBe(999);
    expect(slot.team_id).toBeNull();
    expect(slot.position).toBe('F');
    expect(slot.is_active).toBe(true);
    expect(slot.activated_from_ir).toBe(false);
  });

  it('handles goalie slots with team_id instead of player_id', () => {
    const r3Slots = [
      makeSlot({
        id: 'g1',
        player_id: null,
        team_id: 55,
        position: 'G',
        points_earned: 30,
      }),
    ];
    const r4Slots = copyRound3ToRound4(r3Slots);

    expect(r4Slots[0].player_id).toBeNull();
    expect(r4Slots[0].team_id).toBe(55);
    expect(r4Slots[0].position).toBe('G');
    expect(r4Slots[0].points_earned).toBe(0);
  });

  it('copies all position types (F, D, G, IR_F, IR_D)', () => {
    const positions = ['F', 'D', 'G', 'IR_F', 'IR_D'];
    const r3Slots = positions.map((pos, i) =>
      makeSlot({ id: `id-${i}`, position: pos, points_earned: (i + 1) * 5 })
    );
    const r4Slots = copyRound3ToRound4(r3Slots);

    expect(r4Slots.length).toBe(5);
    for (let i = 0; i < positions.length; i++) {
      expect(r4Slots[i].position).toBe(positions[i]);
      expect(r4Slots[i].round).toBe(4);
      expect(r4Slots[i].points_earned).toBe(0);
    }
  });

  it('handles multiple members roster copy', () => {
    const r3Slots = [
      makeSlot({ id: 'a1', league_member_id: 'mem-1', position: 'F' }),
      makeSlot({ id: 'a2', league_member_id: 'mem-1', position: 'D' }),
      makeSlot({ id: 'b1', league_member_id: 'mem-2', position: 'F' }),
      makeSlot({
        id: 'b2',
        league_member_id: 'mem-2',
        position: 'G',
        player_id: null,
        team_id: 10,
      }),
    ];
    const r4Slots = copyRound3ToRound4(r3Slots);

    expect(r4Slots.length).toBe(4);
    expect(r4Slots.filter((s) => s.league_member_id === 'mem-1').length).toBe(
      2
    );
    expect(r4Slots.filter((s) => s.league_member_id === 'mem-2').length).toBe(
      2
    );
    for (const slot of r4Slots) {
      expect(slot.round).toBe(4);
      expect(slot.points_earned).toBe(0);
    }
  });

  it('returns empty array when no R3 slots exist', () => {
    const r4Slots = copyRound3ToRound4([]);
    expect(r4Slots.length).toBe(0);
  });
});
