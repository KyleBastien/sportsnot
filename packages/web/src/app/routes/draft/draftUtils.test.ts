import { describe, expect, it } from '@rstest/core';
import { getInitialDraftRosterPoints } from './draftUtils';

describe('getInitialDraftRosterPoints', () => {
  it('returns existing skater points from current-round cache', () => {
    expect(
      getInitialDraftRosterPoints({
        playerId: 97,
        teamId: null,
        playoffRound: 2,
        playerStats: [
          {
            player_id: 97,
            goals: 2,
            assists: 3,
          },
        ],
        teamStats: [],
      })
    ).toBe(5);
  });

  it('returns existing goalie/team points from current-round cache', () => {
    expect(
      getInitialDraftRosterPoints({
        playerId: null,
        teamId: 12,
        playoffRound: 2,
        playerStats: [],
        teamStats: [
          {
            team_id: 12,
            wins: 3,
            shutouts: 1,
          },
        ],
      })
    ).toBe(8);
  });

  it('returns zero when drafted asset has not scored yet', () => {
    expect(
      getInitialDraftRosterPoints({
        playerId: 29,
        teamId: null,
        playoffRound: 2,
        playerStats: [],
        teamStats: [],
      })
    ).toBe(0);
  });
});
