import type { Position } from '@sportsnot/types';
import type {
  ComparePlayer,
  DraftMemberRow,
  DraftConfirmPositionOption,
  DraftPickRow,
  DraftStateRow,
  DraftRosterComposition,
  DraftRosterPosition,
  MyRosterGroup,
  MySlotCounts,
} from './draftPageTypes';

export const MAX_COMPARE = 4;

export function sortDraftHistory(picks: DraftPickRow[]): DraftPickRow[] {
  return [...picks].sort((a, b) => (b.pick_number ?? 0) - (a.pick_number ?? 0));
}

export function createEmptySlotCounts(): MySlotCounts {
  return {
    F: 0,
    D: 0,
    G: 0,
    IR_F: 0,
    IR_D: 0,
  };
}

export function countMemberSlots(
  picks: DraftPickRow[],
  memberUserId: string | undefined
): MySlotCounts {
  const counts = createEmptySlotCounts();

  if (!memberUserId) {
    return counts;
  }

  for (const pick of picks) {
    if (pick.league_members?.user_id === memberUserId && pick.position) {
      const slot = pick.position as DraftRosterPosition;
      counts[slot] = (counts[slot] ?? 0) + 1;
    }
  }

  return counts;
}

export function buildMyRosterSlots(
  picks: DraftPickRow[],
  memberUserId: string | undefined,
  roster: DraftRosterComposition
): MyRosterGroup[] {
  const myPicks = memberUserId
    ? picks.filter(
        (pick) =>
          pick.league_members?.user_id === memberUserId &&
          Boolean(pick.position)
      )
    : [];

  const positionConfig: Array<{
    key: DraftRosterPosition;
    label: string;
    max: number;
  }> = [
    { key: 'F', label: 'Forward', max: roster.forwards },
    { key: 'D', label: 'Defenseman', max: roster.defensemen },
    { key: 'G', label: 'Goalie', max: roster.goalies },
    { key: 'IR_F', label: 'IR Forward', max: roster.irForwards },
    { key: 'IR_D', label: 'IR Defenseman', max: roster.irDefensemen },
  ];

  return positionConfig
    .filter(({ max }) => max > 0)
    .map(({ key, label, max }) => {
      const filled = myPicks.filter((pick) => pick.position === key);
      const emptyCount = Math.max(0, max - filled.length);
      return { position: key, label, filled, emptyCount };
    });
}

export function isDraftPositionFull(
  position: string,
  mySlotCounts: MySlotCounts,
  roster: DraftRosterComposition
): boolean {
  if (position === 'F') {
    return (
      mySlotCounts['F'] >= roster.forwards &&
      mySlotCounts['IR_F'] >= roster.irForwards
    );
  }

  if (position === 'D') {
    return (
      mySlotCounts['D'] >= roster.defensemen &&
      mySlotCounts['IR_D'] >= roster.irDefensemen
    );
  }

  if (position === 'G') {
    return mySlotCounts['G'] >= roster.goalies;
  }

  return false;
}

export function getDefaultConfirmPosition(
  position: string,
  mySlotCounts: MySlotCounts,
  roster: DraftRosterComposition
): Position {
  if (position === 'G') {
    return 'G';
  }

  if (position === 'D') {
    const defenseFull = mySlotCounts['D'] >= roster.defensemen;
    const irDefenseFull = mySlotCounts['IR_D'] >= roster.irDefensemen;
    return defenseFull && !irDefenseFull ? 'IR_D' : 'D';
  }

  const forwardsFull = mySlotCounts['F'] >= roster.forwards;
  const irForwardsFull = mySlotCounts['IR_F'] >= roster.irForwards;
  return forwardsFull && !irForwardsFull ? 'IR_F' : 'F';
}

export function isConfirmPositionFull(
  confirmPosition: Position,
  mySlotCounts: MySlotCounts,
  roster: DraftRosterComposition
): boolean {
  switch (confirmPosition) {
    case 'F':
      return mySlotCounts['F'] >= roster.forwards;
    case 'IR_F':
      return mySlotCounts['IR_F'] >= roster.irForwards;
    case 'D':
      return mySlotCounts['D'] >= roster.defensemen;
    case 'IR_D':
      return mySlotCounts['IR_D'] >= roster.irDefensemen;
    case 'G':
      return mySlotCounts['G'] >= roster.goalies;
    default:
      return false;
  }
}

export function buildConfirmPositionOptions(
  position: string,
  mySlotCounts: MySlotCounts,
  roster: DraftRosterComposition,
  allowIrSlots: boolean
): DraftConfirmPositionOption[] {
  if (position === 'G') {
    return [{ label: 'Goalie', value: 'G' }];
  }

  if (position === 'D') {
    const options: DraftConfirmPositionOption[] = [
      {
        label:
          mySlotCounts['D'] >= roster.defensemen ? 'Defense (full)' : 'Defense',
        value: 'D',
        disabled: mySlotCounts['D'] >= roster.defensemen,
      },
    ];

    if (allowIrSlots) {
      options.push({
        label:
          mySlotCounts['IR_D'] >= roster.irDefensemen
            ? 'IR Defense (full)'
            : 'IR Defense',
        value: 'IR_D',
        disabled: mySlotCounts['IR_D'] >= roster.irDefensemen,
      });
    }

    return options;
  }

  const options: DraftConfirmPositionOption[] = [
    {
      label:
        mySlotCounts['F'] >= roster.forwards ? 'Forward (full)' : 'Forward',
      value: 'F',
      disabled: mySlotCounts['F'] >= roster.forwards,
    },
  ];

  if (allowIrSlots) {
    options.push({
      label:
        mySlotCounts['IR_F'] >= roster.irForwards
          ? 'IR Forward (full)'
          : 'IR Forward',
      value: 'IR_F',
      disabled: mySlotCounts['IR_F'] >= roster.irForwards,
    });
  }

  return options;
}

export function toggleComparePlayers(
  previous: ComparePlayer[],
  player: ComparePlayer
): ComparePlayer[] {
  const exists = previous.some((entry) => entry.id === player.id);

  if (exists) {
    return previous.filter((entry) => entry.id !== player.id);
  }

  if (previous.length >= MAX_COMPARE) {
    return previous;
  }

  return [...previous, player];
}

export function removeComparedPlayer(
  previous: ComparePlayer[],
  playerId: number
): ComparePlayer[] {
  return previous.filter((player) => player.id !== playerId);
}

export function createDraftedIdSet(
  picks: DraftPickRow[],
  key: 'player_id' | 'team_id'
): Set<number> {
  return new Set<number>(
    picks.filter((pick) => pick[key]).map((pick) => pick[key] as number)
  );
}

export function buildDraftTurnState(
  draft: DraftStateRow | null,
  members: DraftMemberRow[],
  userId: string | undefined,
  commissionerId: string | null
) {
  const draftOrder = draft?.draft_order ?? [];
  const isDraftComplete =
    draft?.status === 'completed' ||
    (draft ? draft.current_pick > draftOrder.length : false);
  const currentPickIndex =
    draft && draft.current_pick >= 1 && draft.current_pick <= draftOrder.length
      ? draft.current_pick - 1
      : -1;
  const currentPickerUserId =
    currentPickIndex >= 0 ? draftOrder[currentPickIndex] : undefined;
  const isMyTurn = currentPickerUserId === userId;
  const myMember = members.find((member) => member.user_id === userId);
  const currentPicker = members.find(
    (member) => member.user_id === currentPickerUserId
  );
  const isCommissioner = Boolean(
    commissionerId && userId && commissionerId === userId
  );
  const canPick = isMyTurn || (isCommissioner && !isDraftComplete);
  const pickingMember =
    isCommissioner && !isMyTurn
      ? members.find((member) => member.user_id === currentPickerUserId)
      : myMember;

  return {
    draftOrder,
    isDraftComplete,
    currentPicker,
    isMyTurn,
    myMember,
    isCommissioner,
    canPick,
    pickingMember,
  };
}
