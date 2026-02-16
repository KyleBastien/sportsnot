import { describe, it, expect } from '@rstest/core';
import { groupHasActions, SlotLike } from './rosterUtils';

function makeSlot(
  overrides: Partial<SlotLike> & { id: string; position: string }
): SlotLike {
  return {
    is_active: true,
    activated_from_ir: false,
    ...overrides,
  };
}

describe('groupHasActions', () => {
  it('returns false for non-IR groups (Forward)', () => {
    const allSlots = [
      makeSlot({ id: '1', position: 'F' }),
      makeSlot({ id: '2', position: 'IR_F' }),
    ];
    const groupPlayers = [allSlots[0]];
    expect(groupHasActions('F', groupPlayers, allSlots)).toBe(false);
  });

  it('returns false for non-IR groups (Defenseman)', () => {
    const allSlots = [
      makeSlot({ id: '1', position: 'D' }),
      makeSlot({ id: '2', position: 'IR_D' }),
    ];
    const groupPlayers = [allSlots[0]];
    expect(groupHasActions('D', groupPlayers, allSlots)).toBe(false);
  });

  it('returns false for non-IR groups (Goalie)', () => {
    const allSlots = [makeSlot({ id: '1', position: 'G' })];
    expect(groupHasActions('G', allSlots, allSlots)).toBe(false);
  });

  it('returns true for IR_F group when there is an active F to swap', () => {
    const allSlots = [
      makeSlot({ id: 'f1', position: 'F', is_active: true }),
      makeSlot({ id: 'ir1', position: 'IR_F', activated_from_ir: false }),
    ];
    const irGroup = [allSlots[1]];
    expect(groupHasActions('IR_F', irGroup, allSlots)).toBe(true);
  });

  it('returns true for IR_D group when there is an active D to swap', () => {
    const allSlots = [
      makeSlot({ id: 'd1', position: 'D', is_active: true }),
      makeSlot({ id: 'ir1', position: 'IR_D', activated_from_ir: false }),
    ];
    const irGroup = [allSlots[1]];
    expect(groupHasActions('IR_D', irGroup, allSlots)).toBe(true);
  });

  it('returns false for IR_F group when all IR slots already activated', () => {
    const allSlots = [
      makeSlot({ id: 'f1', position: 'F', is_active: true }),
      makeSlot({ id: 'ir1', position: 'IR_F', activated_from_ir: true }),
    ];
    const irGroup = [allSlots[1]];
    expect(groupHasActions('IR_F', irGroup, allSlots)).toBe(false);
  });

  it('returns false for IR_D group when no active D candidates exist', () => {
    const allSlots = [
      makeSlot({ id: 'd1', position: 'D', is_active: false }),
      makeSlot({ id: 'ir1', position: 'IR_D', activated_from_ir: false }),
    ];
    const irGroup = [allSlots[1]];
    expect(groupHasActions('IR_D', irGroup, allSlots)).toBe(false);
  });

  it('returns false for IR_F group when no F slots exist at all', () => {
    const allSlots = [
      makeSlot({ id: 'ir1', position: 'IR_F', activated_from_ir: false }),
    ];
    const irGroup = [allSlots[0]];
    expect(groupHasActions('IR_F', irGroup, allSlots)).toBe(false);
  });

  it('returns true when at least one IR slot is actionable among multiple', () => {
    const allSlots = [
      makeSlot({ id: 'f1', position: 'F', is_active: true }),
      makeSlot({ id: 'ir1', position: 'IR_F', activated_from_ir: true }),
      makeSlot({ id: 'ir2', position: 'IR_F', activated_from_ir: false }),
    ];
    const irGroup = [allSlots[1], allSlots[2]];
    expect(groupHasActions('IR_F', irGroup, allSlots)).toBe(true);
  });

  it('returns false when all IR slots are activated and no actions remain', () => {
    const allSlots = [
      makeSlot({ id: 'f1', position: 'F', is_active: true }),
      makeSlot({ id: 'ir1', position: 'IR_F', activated_from_ir: true }),
      makeSlot({ id: 'ir2', position: 'IR_F', activated_from_ir: true }),
    ];
    const irGroup = [allSlots[1], allSlots[2]];
    expect(groupHasActions('IR_F', irGroup, allSlots)).toBe(false);
  });

  it('returns false for empty group', () => {
    const allSlots = [makeSlot({ id: 'f1', position: 'F', is_active: true })];
    expect(groupHasActions('IR_F', [], allSlots)).toBe(false);
  });
});
