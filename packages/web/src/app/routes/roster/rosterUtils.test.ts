import { describe, it, expect } from '@rstest/core';
import { groupHasActions, SlotLike } from './rosterUtils';

function makeSlot(
  overrides: Partial<SlotLike> & { id: string; position: string }
): SlotLike {
  return {
    is_active: true,
    activated_from_ir: false,
    player_id: null,
    ...overrides,
  };
}

describe('groupHasActions', () => {
  it('returns false for non-IR groups (Forward)', () => {
    const allSlots = [
      makeSlot({ id: '1', position: 'F', player_id: 1 }),
      makeSlot({ id: '2', position: 'IR_F' }),
    ];
    const groupPlayers = [allSlots[0]];
    const injured = new Set([1]);
    expect(groupHasActions('F', groupPlayers, allSlots, injured)).toBe(false);
  });

  it('returns false for non-IR groups (Defenseman)', () => {
    const allSlots = [
      makeSlot({ id: '1', position: 'D', player_id: 1 }),
      makeSlot({ id: '2', position: 'IR_D' }),
    ];
    const groupPlayers = [allSlots[0]];
    const injured = new Set([1]);
    expect(groupHasActions('D', groupPlayers, allSlots, injured)).toBe(false);
  });

  it('returns false for non-IR groups (Goalie)', () => {
    const allSlots = [makeSlot({ id: '1', position: 'G', player_id: 1 })];
    const injured = new Set([1]);
    expect(groupHasActions('G', allSlots, allSlots, injured)).toBe(false);
  });

  it('returns true for IR_F group when there is an active injured F to swap', () => {
    const allSlots = [
      makeSlot({ id: 'f1', position: 'F', is_active: true, player_id: 10 }),
      makeSlot({ id: 'ir1', position: 'IR_F', activated_from_ir: false }),
    ];
    const irGroup = [allSlots[1]];
    const injured = new Set([10]);
    expect(groupHasActions('IR_F', irGroup, allSlots, injured)).toBe(true);
  });

  it('returns true for IR_D group when there is an active injured D to swap', () => {
    const allSlots = [
      makeSlot({ id: 'd1', position: 'D', is_active: true, player_id: 20 }),
      makeSlot({ id: 'ir1', position: 'IR_D', activated_from_ir: false }),
    ];
    const irGroup = [allSlots[1]];
    const injured = new Set([20]);
    expect(groupHasActions('IR_D', irGroup, allSlots, injured)).toBe(true);
  });

  it('returns false for IR_F group when all IR slots already activated', () => {
    const allSlots = [
      makeSlot({ id: 'f1', position: 'F', is_active: true, player_id: 10 }),
      makeSlot({ id: 'ir1', position: 'IR_F', activated_from_ir: true }),
    ];
    const irGroup = [allSlots[1]];
    const injured = new Set([10]);
    expect(groupHasActions('IR_F', irGroup, allSlots, injured)).toBe(false);
  });

  it('returns false for IR_D group when no active D candidates exist', () => {
    const allSlots = [
      makeSlot({
        id: 'd1',
        position: 'D',
        is_active: false,
        player_id: 20,
      }),
      makeSlot({ id: 'ir1', position: 'IR_D', activated_from_ir: false }),
    ];
    const irGroup = [allSlots[1]];
    const injured = new Set([20]);
    expect(groupHasActions('IR_D', irGroup, allSlots, injured)).toBe(false);
  });

  it('returns false for IR_F group when no F slots exist at all', () => {
    const allSlots = [
      makeSlot({ id: 'ir1', position: 'IR_F', activated_from_ir: false }),
    ];
    const irGroup = [allSlots[0]];
    const injured = new Set<number>();
    expect(groupHasActions('IR_F', irGroup, allSlots, injured)).toBe(false);
  });

  it('returns true when at least one IR slot is actionable among multiple', () => {
    const allSlots = [
      makeSlot({ id: 'f1', position: 'F', is_active: true, player_id: 10 }),
      makeSlot({ id: 'ir1', position: 'IR_F', activated_from_ir: true }),
      makeSlot({ id: 'ir2', position: 'IR_F', activated_from_ir: false }),
    ];
    const irGroup = [allSlots[1], allSlots[2]];
    const injured = new Set([10]);
    expect(groupHasActions('IR_F', irGroup, allSlots, injured)).toBe(true);
  });

  it('returns false when all IR slots are activated and no actions remain', () => {
    const allSlots = [
      makeSlot({ id: 'f1', position: 'F', is_active: true, player_id: 10 }),
      makeSlot({ id: 'ir1', position: 'IR_F', activated_from_ir: true }),
      makeSlot({ id: 'ir2', position: 'IR_F', activated_from_ir: true }),
    ];
    const irGroup = [allSlots[1], allSlots[2]];
    const injured = new Set([10]);
    expect(groupHasActions('IR_F', irGroup, allSlots, injured)).toBe(false);
  });

  it('returns false for empty group', () => {
    const allSlots = [
      makeSlot({ id: 'f1', position: 'F', is_active: true, player_id: 10 }),
    ];
    const injured = new Set([10]);
    expect(groupHasActions('IR_F', [], allSlots, injured)).toBe(false);
  });

  // --- Injury-specific tests ---

  it('returns false for IR_F when active F exists but is NOT injured', () => {
    const allSlots = [
      makeSlot({ id: 'f1', position: 'F', is_active: true, player_id: 10 }),
      makeSlot({ id: 'ir1', position: 'IR_F', activated_from_ir: false }),
    ];
    const irGroup = [allSlots[1]];
    const injured = new Set<number>(); // no one injured
    expect(groupHasActions('IR_F', irGroup, allSlots, injured)).toBe(false);
  });

  it('returns false for IR_D when active D exists but is NOT injured', () => {
    const allSlots = [
      makeSlot({ id: 'd1', position: 'D', is_active: true, player_id: 20 }),
      makeSlot({ id: 'ir1', position: 'IR_D', activated_from_ir: false }),
    ];
    const irGroup = [allSlots[1]];
    const injured = new Set<number>();
    expect(groupHasActions('IR_D', irGroup, allSlots, injured)).toBe(false);
  });

  it('returns true only for the injured F among multiple active Fs', () => {
    const allSlots = [
      makeSlot({ id: 'f1', position: 'F', is_active: true, player_id: 10 }),
      makeSlot({ id: 'f2', position: 'F', is_active: true, player_id: 11 }),
      makeSlot({ id: 'ir1', position: 'IR_F', activated_from_ir: false }),
    ];
    const irGroup = [allSlots[2]];
    // Only player 11 is injured
    const injured = new Set([11]);
    expect(groupHasActions('IR_F', irGroup, allSlots, injured)).toBe(true);
  });

  it('returns false when F player_id is null', () => {
    const allSlots = [
      makeSlot({ id: 'f1', position: 'F', is_active: true, player_id: null }),
      makeSlot({ id: 'ir1', position: 'IR_F', activated_from_ir: false }),
    ];
    const irGroup = [allSlots[1]];
    const injured = new Set<number>();
    expect(groupHasActions('IR_F', irGroup, allSlots, injured)).toBe(false);
  });

  it('returns false when injured player is a different position', () => {
    const allSlots = [
      makeSlot({ id: 'f1', position: 'F', is_active: true, player_id: 10 }),
      makeSlot({ id: 'd1', position: 'D', is_active: true, player_id: 20 }),
      makeSlot({ id: 'ir1', position: 'IR_F', activated_from_ir: false }),
    ];
    const irGroup = [allSlots[2]];
    // Only the D is injured, not the F
    const injured = new Set([20]);
    expect(groupHasActions('IR_F', irGroup, allSlots, injured)).toBe(false);
  });
});
