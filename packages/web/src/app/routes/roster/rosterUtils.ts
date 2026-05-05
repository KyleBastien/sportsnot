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

const POSITION_LABELS: Record<string, string> = {
  F: 'Forward',
  D: 'Defenseman',
  G: 'Goalie',
  IR_F: 'IR Forward',
  IR_D: 'IR Defenseman',
};

const POSITION_ORDER = ['F', 'D', 'G', 'IR_F', 'IR_D'];

export function buildPositionOrder(allowIrSlots: boolean): string[] {
  return allowIrSlots
    ? POSITION_ORDER
    : POSITION_ORDER.filter(
        (position) => position !== 'IR_F' && position !== 'IR_D'
      );
}

export function buildRosterTitle(
  isOwnRoster: boolean,
  viewedTeamName: string | undefined
): string {
  return isOwnRoster ? 'My Roster' : `${viewedTeamName ?? 'Roster'}`;
}

export function buildMemberOptions(
  leagueMembers: Array<{
    id: string;
    user_id: string;
    team_name: string;
    users?: { display_name?: string } | null;
  }>,
  userId: string | undefined
): Array<{ value: string; label: string }> {
  return leagueMembers.map((member) => ({
    value: member.id,
    label:
      member.user_id === userId
        ? `${member.team_name} (You)`
        : `${member.team_name} — ${member.users?.display_name ?? 'Unknown'}`,
  }));
}

export function getSelectedMemberId(
  leagueMemberId: string | undefined,
  myMemberId: string | undefined
): string {
  return leagueMemberId ?? myMemberId ?? '';
}

export function groupRosterSlots<T extends { position: string }>(
  slots: T[],
  positionOrder: string[]
): Array<{ position: string; label: string; players: T[] }> {
  return positionOrder.map((position) => ({
    position,
    label: POSITION_LABELS[position],
    players: slots.filter((slot) => slot.position === position),
  }));
}

export function getRoundPoints(
  slots: Array<{ is_active: boolean; points_earned: number }>
): number {
  return slots
    .filter((slot) => slot.is_active)
    .reduce((sum, slot) => sum + (slot.points_earned ?? 0), 0);
}

export function resolveRosterNavigation(
  leagueId: string,
  selectedMemberId: string | null,
  myMemberId: string | undefined
): string {
  if (!selectedMemberId || selectedMemberId === myMemberId) {
    return `/roster/${leagueId}`;
  }

  return `/roster/${leagueId}/${selectedMemberId}`;
}

export function getSlotNhlTeamAbbreviation(
  slot: { player_id: number | null; team_id: number | null },
  playerTeamAbbreviationMap: Map<number, string>,
  teamAbbreviationMap: Map<number, string>
): string {
  if (slot.player_id != null) {
    return playerTeamAbbreviationMap.get(slot.player_id) ?? '—';
  }

  if (slot.team_id != null) {
    return teamAbbreviationMap.get(slot.team_id) ?? '—';
  }

  return '—';
}

export function getInjuredReplacementCandidates<T extends SlotLike>(
  irSlot: T,
  allSlots: T[],
  injuredPlayerIds: Set<number>
): T[] {
  if (irSlot.position !== 'IR_F' && irSlot.position !== 'IR_D') {
    return [];
  }

  const matchingPosition = irSlot.position === 'IR_F' ? 'F' : 'D';

  return allSlots.filter(
    (slot) =>
      slot.position === matchingPosition &&
      slot.is_active &&
      slot.id !== irSlot.id &&
      slot.player_id !== null &&
      injuredPlayerIds.has(slot.player_id)
  );
}

export function groupHasActions(
  groupPosition: string,
  groupPlayers: SlotLike[],
  allSlots: SlotLike[],
  injuredPlayerIds: Set<number>
): boolean {
  const isIrGroup = groupPosition === 'IR_F' || groupPosition === 'IR_D';
  if (!isIrGroup) return false;

  return groupPlayers.some(
    (slot) =>
      !slot.activated_from_ir &&
      getInjuredReplacementCandidates(slot, allSlots, injuredPlayerIds).length >
        0
  );
}
