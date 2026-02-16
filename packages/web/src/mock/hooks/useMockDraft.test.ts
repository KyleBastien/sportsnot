import { describe, it, expect } from '@rstest/core';
import { generateSnakeDraftOrder } from './useMockDraft';

describe('generateSnakeDraftOrder', () => {
  it('should generate correct snake pattern for 3 members and 3 rounds', () => {
    const order = generateSnakeDraftOrder(['A', 'B', 'C'], 3);
    // Round 0 (even): A,B,C  Round 1 (odd): C,B,A  Round 2 (even): A,B,C
    expect(order).toEqual(['A', 'B', 'C', 'C', 'B', 'A', 'A', 'B', 'C']);
  });

  it('should reverse order on odd rounds', () => {
    const order = generateSnakeDraftOrder(['X', 'Y'], 2);
    // Round 0: X,Y  Round 1: Y,X
    expect(order).toEqual(['X', 'Y', 'Y', 'X']);
  });

  it('should return empty array for 0 rounds', () => {
    expect(generateSnakeDraftOrder(['A', 'B'], 0)).toEqual([]);
  });

  it('should handle single member', () => {
    const order = generateSnakeDraftOrder(['A'], 3);
    expect(order).toEqual(['A', 'A', 'A']);
  });

  it('should generate 11 draft rounds (hockey roster) correctly', () => {
    const members = ['worst', 'mid', 'best'];
    const order = generateSnakeDraftOrder(members, 11);
    // Total picks = 3 members * 11 rounds = 33
    expect(order.length).toBe(33);
    // First pick goes to worst team (index 0 of input)
    expect(order[0]).toBe('worst');
    // Last pick of round 0 goes to best
    expect(order[2]).toBe('best');
    // First pick of round 1 (odd) goes to best (reversed)
    expect(order[3]).toBe('best');
    // Last pick of round 1 goes to worst
    expect(order[5]).toBe('worst');
  });

  it('should preserve input order as-is (caller sorts by standings)', () => {
    // If caller passes [worst, mid, best], worst gets first pick in even rounds
    const order = generateSnakeDraftOrder(['worst', 'mid', 'best'], 1);
    expect(order).toEqual(['worst', 'mid', 'best']);
  });
});
