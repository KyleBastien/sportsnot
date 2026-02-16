import { describe, it, expect } from '@rstest/core';
import { deriveCurrentRound, deriveNextRound } from './roundUtils';

describe('roundUtils', () => {
  describe('deriveCurrentRound', () => {
    it('should use league.current_round when it is a positive number', () => {
      expect(deriveCurrentRound(2, 1)).toBe(2);
    });

    it('should fall back to completedDraftsCount when current_round is 0', () => {
      expect(deriveCurrentRound(0, 1)).toBe(1);
    });

    it('should fall back to completedDraftsCount when current_round is null', () => {
      expect(deriveCurrentRound(null, 2)).toBe(2);
    });

    it('should fall back to completedDraftsCount when current_round is undefined', () => {
      expect(deriveCurrentRound(undefined, 3)).toBe(3);
    });

    it('should return 0 when both are 0/undefined', () => {
      expect(deriveCurrentRound(0, 0)).toBe(0);
      expect(deriveCurrentRound(null, 0)).toBe(0);
      expect(deriveCurrentRound(undefined, 0)).toBe(0);
    });
  });

  describe('deriveNextRound', () => {
    it('should return 2 after Round 1 completes (current_round=0, 1 completed draft)', () => {
      expect(deriveNextRound(0, 1)).toBe(2);
    });

    it('should return 2 after Round 1 completes (current_round=null, 1 completed draft)', () => {
      expect(deriveNextRound(null, 1)).toBe(2);
    });

    it('should return 3 after Round 2 completes (current_round=0, 2 completed drafts)', () => {
      expect(deriveNextRound(0, 2)).toBe(3);
    });

    it('should return 3 when current_round is correctly set to 2', () => {
      expect(deriveNextRound(2, 2)).toBe(3);
    });

    it('should return 4 after Round 3 completes', () => {
      expect(deriveNextRound(0, 3)).toBe(4);
      expect(deriveNextRound(3, 3)).toBe(4);
    });

    it('should return 1 when no drafts have been completed (initial state)', () => {
      expect(deriveNextRound(0, 0)).toBe(1);
    });
  });
});
