import { describe, it, expect } from '@rstest/core';

/**
 * Pure logic tests for LeagueDashboardPage button visibility.
 *
 * These mirror the conditions in the JSX to ensure the
 * "Start Next Draft" and "Advance to Finals" buttons are
 * shown/hidden based on round, role, and completion state.
 */

interface ButtonVisibilityInput {
  isCommissioner: boolean;
  seasonComplete: boolean;
  currentRound: number;
  roundComplete: boolean;
  leagueStatus: string;
}

/** Mirrors the JSX condition for "Start Next Draft" */
function showStartNextDraft(input: ButtonVisibilityInput): boolean {
  return (
    input.leagueStatus === 'active' &&
    input.isCommissioner &&
    !input.seasonComplete &&
    input.currentRound < 3
  );
}

/** Mirrors the JSX condition for "Advance to Finals" */
function showAdvanceToFinals(input: ButtonVisibilityInput): boolean {
  return (
    input.leagueStatus === 'active' &&
    input.isCommissioner &&
    input.currentRound === 3 &&
    input.roundComplete &&
    !input.seasonComplete
  );
}

/** Mirrors the disabled state on the Start Next Draft button */
function isStartNextDraftDisabled(
  roundComplete: boolean,
  roundStatusLoading: boolean
): boolean {
  return !roundComplete || roundStatusLoading;
}

function makeInput(
  overrides: Partial<ButtonVisibilityInput> = {}
): ButtonVisibilityInput {
  return {
    isCommissioner: true,
    seasonComplete: false,
    currentRound: 1,
    roundComplete: false,
    leagueStatus: 'active',
    ...overrides,
  };
}

describe('LeagueDashboardPage button visibility', () => {
  describe('Start Next Draft', () => {
    it('shows for commissioner in R1 active league', () => {
      expect(showStartNextDraft(makeInput({ currentRound: 1 }))).toBe(true);
    });

    it('shows for commissioner in R2 active league', () => {
      expect(showStartNextDraft(makeInput({ currentRound: 2 }))).toBe(true);
    });

    it('hides when current_round >= 3', () => {
      expect(showStartNextDraft(makeInput({ currentRound: 3 }))).toBe(false);
      expect(showStartNextDraft(makeInput({ currentRound: 4 }))).toBe(false);
    });

    it('hides for non-commissioner', () => {
      expect(showStartNextDraft(makeInput({ isCommissioner: false }))).toBe(
        false
      );
    });

    it('hides when season is complete', () => {
      expect(showStartNextDraft(makeInput({ seasonComplete: true }))).toBe(
        false
      );
    });

    it('hides when league status is not active', () => {
      expect(showStartNextDraft(makeInput({ leagueStatus: 'drafting' }))).toBe(
        false
      );
      expect(showStartNextDraft(makeInput({ leagueStatus: 'setup' }))).toBe(
        false
      );
    });

    it('is disabled when round is not complete', () => {
      expect(isStartNextDraftDisabled(false, false)).toBe(true);
    });

    it('is disabled when loading', () => {
      expect(isStartNextDraftDisabled(true, true)).toBe(true);
    });

    it('is enabled when round is complete and not loading', () => {
      expect(isStartNextDraftDisabled(true, false)).toBe(false);
    });
  });

  describe('Advance to Finals', () => {
    it('shows for commissioner at R3 when round is complete', () => {
      expect(
        showAdvanceToFinals(makeInput({ currentRound: 3, roundComplete: true }))
      ).toBe(true);
    });

    it('hides when current_round !== 3', () => {
      expect(
        showAdvanceToFinals(makeInput({ currentRound: 2, roundComplete: true }))
      ).toBe(false);
      expect(
        showAdvanceToFinals(makeInput({ currentRound: 4, roundComplete: true }))
      ).toBe(false);
    });

    it('hides when round is not complete', () => {
      expect(
        showAdvanceToFinals(
          makeInput({ currentRound: 3, roundComplete: false })
        )
      ).toBe(false);
    });

    it('hides for non-commissioner', () => {
      expect(
        showAdvanceToFinals(
          makeInput({
            currentRound: 3,
            roundComplete: true,
            isCommissioner: false,
          })
        )
      ).toBe(false);
    });

    it('hides when season is complete', () => {
      expect(
        showAdvanceToFinals(
          makeInput({
            currentRound: 3,
            roundComplete: true,
            seasonComplete: true,
          })
        )
      ).toBe(false);
    });

    it('hides when league status is not active', () => {
      expect(
        showAdvanceToFinals(
          makeInput({
            currentRound: 3,
            roundComplete: true,
            leagueStatus: 'drafting',
          })
        )
      ).toBe(false);
    });
  });

  describe('mutual exclusivity', () => {
    it('Start Next Draft and Advance to Finals are never both visible', () => {
      const rounds = [1, 2, 3, 4];
      const bools = [true, false];
      for (const round of rounds) {
        for (const complete of bools) {
          for (const season of bools) {
            const input = makeInput({
              currentRound: round,
              roundComplete: complete,
              seasonComplete: season,
            });
            const startDraft = showStartNextDraft(input);
            const advanceFinals = showAdvanceToFinals(input);
            expect(startDraft && advanceFinals).toBe(false);
          }
        }
      }
    });
  });
});
