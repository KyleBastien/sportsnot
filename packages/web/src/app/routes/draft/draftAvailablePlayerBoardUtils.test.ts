import { describe, expect, it } from '@rstest/core';
import {
  buildSkaterRows,
  buildTeamRows,
  filterTeamRows,
} from './draftAvailablePlayerBoardUtils';

describe('draftAvailablePlayerBoardUtils', () => {
  it('uses cumulative playoff totals for later-round skater rows', () => {
    const rows = buildSkaterRows({
      playerStats: [
        {
          player_id: 97,
          player_name: 'Connor McDavid',
          position: 'F',
          team_abbreviation: 'EDM',
          is_injured: false,
          goals: 0,
          assists: 0,
          games_played: 1,
        },
      ],
      cumulativePlayerStats: [
        {
          player_id: 97,
          player_name: 'Connor McDavid',
          position: 'F',
          team_abbreviation: 'EDM',
          is_injured: false,
          goals: 5,
          assists: 7,
          games_played: 9,
        },
      ],
      regSeasonStats: [],
      draftedPlayerIds: new Set<number>(),
      isRound1: false,
    });

    expect(rows).toEqual([
      expect.objectContaining({
        id: 97,
        goals: 5,
        assists: 7,
        points: 12,
        gamesPlayed: 9,
      }),
    ]);
  });

  it('uses cumulative playoff totals for team rows and sorts by wins then shutouts', () => {
    const rows = filterTeamRows({
      teamRows: buildTeamRows({
        teamStats: [
          {
            team_id: 1,
            team_name: 'Edmonton Oilers',
            team_abbreviation: 'EDM',
            is_eliminated: false,
            wins: 0,
            shutouts: 0,
          },
          {
            team_id: 2,
            team_name: 'Dallas Stars',
            team_abbreviation: 'DAL',
            is_eliminated: false,
            wins: 0,
            shutouts: 0,
          },
        ],
        cumulativeTeamStats: [
          {
            team_id: 1,
            team_name: 'Edmonton Oilers',
            team_abbreviation: 'EDM',
            is_eliminated: false,
            wins: 6,
            shutouts: 1,
          },
          {
            team_id: 2,
            team_name: 'Dallas Stars',
            team_abbreviation: 'DAL',
            is_eliminated: false,
            wins: 6,
            shutouts: 2,
          },
        ],
        draftedTeamIds: new Set<number>(),
      }),
      positionFilter: 'ALL',
      searchQuery: '',
    });

    expect(rows[0]).toEqual(
      expect.objectContaining({
        teamId: 2,
        wins: 6,
        shutouts: 2,
      })
    );
    expect(rows[1]).toEqual(
      expect.objectContaining({
        teamId: 1,
        wins: 6,
        shutouts: 1,
      })
    );
  });
});
