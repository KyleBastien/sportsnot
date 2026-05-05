import { describe, expect, it } from '@rstest/core';
import {
  buildConfirmPositionOptions,
  buildMyRosterSlots,
  createEmptySlotCounts,
  getDefaultConfirmPosition,
  isConfirmPositionFull,
  sortDraftHistory,
} from './draftPageHelpers';
import type {
  DraftPickRow,
  DraftRosterComposition,
  MySlotCounts,
} from './draftPageTypes';

function makePick(n: number): DraftPickRow {
  return {
    id: `pick-${n}`,
    pick_number: n,
    player_id: n * 100,
    team_id: null,
    position: 'F',
    league_members: { team_name: `Team ${n}`, user_id: `user-${n}` },
  };
}

const ROSTER_COMPOSITION: DraftRosterComposition = {
  forwards: 5,
  defensemen: 3,
  goalies: 1,
  irForwards: 1,
  irDefensemen: 1,
};

describe('Draft History rendering logic', () => {
  it('sorts picks in descending order by pick_number', () => {
    const picks = [makePick(1), makePick(3), makePick(2)];
    const sorted = sortDraftHistory(picks);
    expect(sorted.map((pick) => pick.pick_number)).toEqual([3, 2, 1]);
  });

  it('returns all picks without truncation (no .slice limit)', () => {
    const picks = Array.from({ length: 25 }, (_, index) => makePick(index + 1));
    const sorted = sortDraftHistory(picks);
    expect(sorted.length).toBe(25);
    expect(sorted[0].pick_number).toBe(25);
    expect(sorted[24].pick_number).toBe(1);
  });

  it('handles more than 10 picks (previous limit was 10)', () => {
    const picks = Array.from({ length: 15 }, (_, index) => makePick(index + 1));
    const sorted = sortDraftHistory(picks);
    expect(sorted.length).toBe(15);
    for (let index = 0; index < 15; index += 1) {
      expect(sorted[index].pick_number).toBe(15 - index);
    }
  });

  it('returns empty array for empty picks', () => {
    const sorted = sortDraftHistory([]);
    expect(sorted.length).toBe(0);
  });

  it('does not mutate the original picks array', () => {
    const picks = [makePick(2), makePick(1), makePick(3)];
    const original = [...picks];
    sortDraftHistory(picks);
    expect(picks.map((pick) => pick.pick_number)).toEqual(
      original.map((pick) => pick.pick_number)
    );
  });

  it('handles large draft (60+ picks for a full league draft)', () => {
    const picks = Array.from({ length: 64 }, (_, index) => makePick(index + 1));
    const sorted = sortDraftHistory(picks);
    expect(sorted.length).toBe(64);
    expect(sorted[0].pick_number).toBe(64);
    expect(sorted[63].pick_number).toBe(1);
  });
});

describe('My Team roster grouping logic', () => {
  it('returns all position groups with correct empty counts when no picks', () => {
    const slots = buildMyRosterSlots([], 'user-1', ROSTER_COMPOSITION);
    expect(slots.length).toBe(5);
    expect(slots.find((slot) => slot.position === 'F')?.emptyCount).toBe(5);
    expect(slots.find((slot) => slot.position === 'D')?.emptyCount).toBe(3);
    expect(slots.find((slot) => slot.position === 'G')?.emptyCount).toBe(1);
    expect(slots.find((slot) => slot.position === 'IR_F')?.emptyCount).toBe(1);
    expect(slots.find((slot) => slot.position === 'IR_D')?.emptyCount).toBe(1);
  });

  it('groups my picks by position and decrements empty counts', () => {
    const picks: DraftPickRow[] = [
      {
        ...makePick(1),
        position: 'F',
        league_members: { team_name: 'A', user_id: 'me' },
      },
      {
        ...makePick(2),
        position: 'F',
        league_members: { team_name: 'A', user_id: 'me' },
      },
      {
        ...makePick(3),
        position: 'D',
        league_members: { team_name: 'A', user_id: 'me' },
      },
    ];
    const slots = buildMyRosterSlots(picks, 'me', ROSTER_COMPOSITION);
    const forwardsGroup = slots.find((slot) => slot.position === 'F')!;
    expect(forwardsGroup.filled.length).toBe(2);
    expect(forwardsGroup.emptyCount).toBe(3);
    const defenseGroup = slots.find((slot) => slot.position === 'D')!;
    expect(defenseGroup.filled.length).toBe(1);
    expect(defenseGroup.emptyCount).toBe(2);
  });

  it('excludes other users picks', () => {
    const picks: DraftPickRow[] = [
      {
        ...makePick(1),
        position: 'F',
        league_members: { team_name: 'A', user_id: 'me' },
      },
      {
        ...makePick(2),
        position: 'F',
        league_members: { team_name: 'B', user_id: 'other' },
      },
    ];
    const slots = buildMyRosterSlots(picks, 'me', ROSTER_COMPOSITION);
    const forwardsGroup = slots.find((slot) => slot.position === 'F')!;
    expect(forwardsGroup.filled.length).toBe(1);
    expect(forwardsGroup.emptyCount).toBe(4);
  });

  it('shows zero empty slots when position is fully filled', () => {
    const picks: DraftPickRow[] = Array.from({ length: 5 }, (_, index) => ({
      ...makePick(index + 1),
      position: 'F',
      league_members: { team_name: 'A', user_id: 'me' },
    }));
    const slots = buildMyRosterSlots(picks, 'me', ROSTER_COMPOSITION);
    const forwardsGroup = slots.find((slot) => slot.position === 'F')!;
    expect(forwardsGroup.filled.length).toBe(5);
    expect(forwardsGroup.emptyCount).toBe(0);
  });

  it('handles goalie picks with team_id (no player_id)', () => {
    const picks: DraftPickRow[] = [
      {
        id: 'g1',
        pick_number: 1,
        player_id: null,
        team_id: 55,
        position: 'G',
        league_members: { team_name: 'A', user_id: 'me' },
      },
    ];
    const slots = buildMyRosterSlots(picks, 'me', ROSTER_COMPOSITION);
    const goaliesGroup = slots.find((slot) => slot.position === 'G')!;
    expect(goaliesGroup.filled.length).toBe(1);
    expect(goaliesGroup.emptyCount).toBe(0);
  });

  it('updates in real-time as new picks are added', () => {
    const picks1: DraftPickRow[] = [
      {
        ...makePick(1),
        position: 'F',
        league_members: { team_name: 'A', user_id: 'me' },
      },
    ];
    const slots1 = buildMyRosterSlots(picks1, 'me', ROSTER_COMPOSITION);
    expect(slots1.find((slot) => slot.position === 'F')!.filled.length).toBe(1);

    const picks2 = [
      ...picks1,
      {
        ...makePick(2),
        position: 'D',
        league_members: { team_name: 'A', user_id: 'me' },
      },
    ];
    const slots2 = buildMyRosterSlots(picks2, 'me', ROSTER_COMPOSITION);
    expect(slots2.find((slot) => slot.position === 'F')!.filled.length).toBe(1);
    expect(slots2.find((slot) => slot.position === 'D')!.filled.length).toBe(1);
  });
});

describe('Draft confirm slot selection helpers', () => {
  it('defaults skaters into IR when the active slot is full but IR is open', () => {
    const counts: MySlotCounts = {
      ...createEmptySlotCounts(),
      F: ROSTER_COMPOSITION.forwards,
    };

    expect(getDefaultConfirmPosition('F', counts, ROSTER_COMPOSITION)).toBe(
      'IR_F'
    );
  });

  it('flags a specific confirm position as full only for that slot', () => {
    const counts: MySlotCounts = {
      ...createEmptySlotCounts(),
      D: ROSTER_COMPOSITION.defensemen,
    };

    expect(isConfirmPositionFull('D', counts, ROSTER_COMPOSITION)).toBe(true);
    expect(isConfirmPositionFull('IR_D', counts, ROSTER_COMPOSITION)).toBe(
      false
    );
  });

  it('builds IR options only when IR slots are enabled', () => {
    const withIr = buildConfirmPositionOptions(
      'F',
      createEmptySlotCounts(),
      ROSTER_COMPOSITION,
      true
    );
    const withoutIr = buildConfirmPositionOptions(
      'F',
      createEmptySlotCounts(),
      ROSTER_COMPOSITION,
      false
    );

    expect(withIr.map((option) => option.value)).toEqual(['F', 'IR_F']);
    expect(withoutIr.map((option) => option.value)).toEqual(['F']);
  });
});
