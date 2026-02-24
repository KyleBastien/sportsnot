/**
 * Determines whether any slot in a position group has an available action.
 * Currently the only action is "Activate IR" which requires:
 * 1. The group is an IR position (IR_F or IR_D)
 * 2. At least one slot in the group has not been activated from IR
 * 3. There is at least one active, injured player at the matching position
 */

export interface SlotLike {
  id: string;
  position: string;
  is_active: boolean;
  activated_from_ir: boolean;
  player_id: number | null;
}

export function groupHasActions(
  groupPosition: string,
  groupPlayers: SlotLike[],
  allSlots: SlotLike[],
  injuredPlayerIds: Set<number>
): boolean {
  const isIrGroup = groupPosition === 'IR_F' || groupPosition === 'IR_D';
  if (!isIrGroup) return false;

  const matchingPos = groupPosition === 'IR_F' ? 'F' : 'D';

  return groupPlayers.some(
    (slot) =>
      !slot.activated_from_ir &&
      allSlots.some(
        (s) =>
          s.position === matchingPos &&
          s.is_active &&
          s.id !== slot.id &&
          s.player_id !== null &&
          injuredPlayerIds.has(s.player_id)
      )
  );
}
