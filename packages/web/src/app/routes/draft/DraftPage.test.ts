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
