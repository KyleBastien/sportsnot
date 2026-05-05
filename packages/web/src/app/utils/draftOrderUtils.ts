import { getRosterComposition } from '@sportsnot/types';
import { generateSnakeDraftOrder, shuffleArray } from '@sportsnot/utils';

interface DraftOrderMember {
  user_id: string;
  team_name: string;
  total_points?: number | null;
}

export function sortMembersForReDraft<
  T extends { total_points?: number | null; team_name: string },
>(members: T[]): T[] {
  return [...members].sort((a, b) => {
    const ptsDiff = (a.total_points ?? 0) - (b.total_points ?? 0);
    if (ptsDiff !== 0) return ptsDiff;
    return a.team_name.localeCompare(b.team_name);
  });
}

function getPicksPerMember(allowIrSlots: boolean): number {
  const rosterComp = getRosterComposition(allowIrSlots);
  return (
    rosterComp.forwards +
    rosterComp.defensemen +
    rosterComp.goalies +
    rosterComp.irForwards +
    rosterComp.irDefensemen
  );
}

function buildSnakeDraftOrderForRoster(
  participantIds: string[],
  allowIrSlots: boolean
): string[] {
  return generateSnakeDraftOrder(
    participantIds,
    getPicksPerMember(allowIrSlots)
  );
}

export function buildInitialDraftOrder<T extends DraftOrderMember>(
  members: T[],
  allowIrSlots: boolean,
  shuffleParticipants: <U>(participants: U[]) => U[] = shuffleArray
): string[] {
  return buildSnakeDraftOrderForRoster(
    shuffleParticipants(members.map((member) => member.user_id)),
    allowIrSlots
  );
}

export function buildReDraftOrder<T extends DraftOrderMember>(
  members: T[],
  allowIrSlots: boolean
): string[] {
  return buildSnakeDraftOrderForRoster(
    sortMembersForReDraft(members).map((member) => member.user_id),
    allowIrSlots
  );
}

export function buildDraftOrder<T extends DraftOrderMember>(
  members: T[],
  allowIrSlots: boolean,
  round: number,
  shuffleParticipants: <U>(participants: U[]) => U[] = shuffleArray
): string[] {
  if (round <= 1) {
    return buildInitialDraftOrder(members, allowIrSlots, shuffleParticipants);
  }

  return buildReDraftOrder(members, allowIrSlots);
}
