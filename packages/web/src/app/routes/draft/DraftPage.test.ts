import { describe, it, expect } from '@rstest/core';

/**
 * Unit tests for DraftPage draft history rendering logic.
 * Tests the sorting and display behavior after removing .slice(0,10) limit.
 */

interface MinimalPick {
  id: string;
  pick_number: number;
  player_id: number | null;
  team_id: number | null;
  position: string;
  league_members?: { team_name: string; user_id: string } | null;
}

function makePick(n: number): MinimalPick {
  return {
    id: `pick-${n}`,
    pick_number: n,
    player_id: n * 100,
    team_id: null,
    position: 'F',
    league_members: { team_name: `Team ${n}`, user_id: `user-${n}` },
  };
}

/** Replicates the draft history sort logic from DraftPage */
function sortedDraftHistory(picks: MinimalPick[]): MinimalPick[] {
  return [...picks].sort((a, b) => (b.pick_number ?? 0) - (a.pick_number ?? 0));
}

describe('Draft History rendering logic', () => {
  it('sorts picks in descending order by pick_number', () => {
    const picks = [makePick(1), makePick(3), makePick(2)];
    const sorted = sortedDraftHistory(picks);
    expect(sorted.map((p) => p.pick_number)).toEqual([3, 2, 1]);
  });

  it('returns all picks without truncation (no .slice limit)', () => {
    const picks = Array.from({ length: 25 }, (_, i) => makePick(i + 1));
    const sorted = sortedDraftHistory(picks);
    expect(sorted.length).toBe(25);
    expect(sorted[0].pick_number).toBe(25);
    expect(sorted[24].pick_number).toBe(1);
  });

  it('handles more than 10 picks (previous limit was 10)', () => {
    const picks = Array.from({ length: 15 }, (_, i) => makePick(i + 1));
    const sorted = sortedDraftHistory(picks);
    expect(sorted.length).toBe(15);
    // All picks from 15 down to 1 are present
    for (let i = 0; i < 15; i++) {
      expect(sorted[i].pick_number).toBe(15 - i);
    }
  });

  it('returns empty array for empty picks', () => {
    const sorted = sortedDraftHistory([]);
    expect(sorted.length).toBe(0);
  });

  it('does not mutate the original picks array', () => {
    const picks = [makePick(2), makePick(1), makePick(3)];
    const original = [...picks];
    sortedDraftHistory(picks);
    expect(picks.map((p) => p.pick_number)).toEqual(
      original.map((p) => p.pick_number)
    );
  });

  it('handles large draft (60+ picks for a full league draft)', () => {
    const picks = Array.from({ length: 64 }, (_, i) => makePick(i + 1));
    const sorted = sortedDraftHistory(picks);
    expect(sorted.length).toBe(64);
    expect(sorted[0].pick_number).toBe(64);
    expect(sorted[63].pick_number).toBe(1);
  });
});

const ROSTER_COMPOSITION = {
  forwards: 5,
  defensemen: 3,
  goalies: 1,
  irForwards: 1,
  irDefensemen: 1,
} as const;

interface RosterGroup {
  position: string;
  label: string;
  filled: MinimalPick[];
  emptyCount: number;
}

/**
 * Replicates the myRosterSlots logic from DraftPage.
 * Groups the user's picks by position with empty slot placeholders.
 */
function buildMyRosterSlots(
  picks: MinimalPick[],
  userId: string
): RosterGroup[] {
  const myPicks = picks.filter(
    (p) => p.league_members?.user_id === userId && p.position
  );

  const positionConfig = [
    { key: 'F', label: 'Forward', max: ROSTER_COMPOSITION.forwards },
    { key: 'D', label: 'Defenseman', max: ROSTER_COMPOSITION.defensemen },
    { key: 'G', label: 'Goalie', max: ROSTER_COMPOSITION.goalies },
    { key: 'IR_F', label: 'IR Forward', max: ROSTER_COMPOSITION.irForwards },
    {
      key: 'IR_D',
      label: 'IR Defenseman',
      max: ROSTER_COMPOSITION.irDefensemen,
    },
  ];

  return positionConfig.map(({ key, label, max }) => {
    const filled = myPicks.filter((p) => p.position === key);
    const emptyCount = Math.max(0, max - filled.length);
    return { position: key, label, filled, emptyCount };
  });
}

describe('My Team roster grouping logic', () => {
  it('returns all position groups with correct empty counts when no picks', () => {
    const slots = buildMyRosterSlots([], 'user-1');
    expect(slots.length).toBe(5);
    expect(slots.find((s) => s.position === 'F')?.emptyCount).toBe(5);
    expect(slots.find((s) => s.position === 'D')?.emptyCount).toBe(3);
    expect(slots.find((s) => s.position === 'G')?.emptyCount).toBe(1);
    expect(slots.find((s) => s.position === 'IR_F')?.emptyCount).toBe(1);
    expect(slots.find((s) => s.position === 'IR_D')?.emptyCount).toBe(1);
  });

  it('groups my picks by position and decrements empty counts', () => {
    const picks: MinimalPick[] = [
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
    const slots = buildMyRosterSlots(picks, 'me');
    const fGroup = slots.find((s) => s.position === 'F')!;
    expect(fGroup.filled.length).toBe(2);
    expect(fGroup.emptyCount).toBe(3);
    const dGroup = slots.find((s) => s.position === 'D')!;
    expect(dGroup.filled.length).toBe(1);
    expect(dGroup.emptyCount).toBe(2);
  });

  it('excludes other users picks', () => {
    const picks: MinimalPick[] = [
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
    const slots = buildMyRosterSlots(picks, 'me');
    const fGroup = slots.find((s) => s.position === 'F')!;
    expect(fGroup.filled.length).toBe(1);
    expect(fGroup.emptyCount).toBe(4);
  });

  it('shows zero empty slots when position is fully filled', () => {
    const picks: MinimalPick[] = Array.from({ length: 5 }, (_, i) => ({
      ...makePick(i + 1),
      position: 'F',
      league_members: { team_name: 'A', user_id: 'me' },
    }));
    const slots = buildMyRosterSlots(picks, 'me');
    const fGroup = slots.find((s) => s.position === 'F')!;
    expect(fGroup.filled.length).toBe(5);
    expect(fGroup.emptyCount).toBe(0);
  });

  it('handles goalie picks with team_id (no player_id)', () => {
    const picks: MinimalPick[] = [
      {
        id: 'g1',
        pick_number: 1,
        player_id: null,
        team_id: 55,
        position: 'G',
        league_members: { team_name: 'A', user_id: 'me' },
      },
    ];
    const slots = buildMyRosterSlots(picks, 'me');
    const gGroup = slots.find((s) => s.position === 'G')!;
    expect(gGroup.filled.length).toBe(1);
    expect(gGroup.emptyCount).toBe(0);
  });

  it('updates in real-time as new picks are added', () => {
    const picks1: MinimalPick[] = [
      {
        ...makePick(1),
        position: 'F',
        league_members: { team_name: 'A', user_id: 'me' },
      },
    ];
    const slots1 = buildMyRosterSlots(picks1, 'me');
    expect(slots1.find((s) => s.position === 'F')!.filled.length).toBe(1);

    const picks2 = [
      ...picks1,
      {
        ...makePick(2),
        position: 'D',
        league_members: { team_name: 'A', user_id: 'me' },
      },
    ];
    const slots2 = buildMyRosterSlots(picks2, 'me');
    expect(slots2.find((s) => s.position === 'F')!.filled.length).toBe(1);
    expect(slots2.find((s) => s.position === 'D')!.filled.length).toBe(1);
  });
});
