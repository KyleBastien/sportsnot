import { describe, expect, it } from '@rstest/core';
import {
  buildStandingsMembers,
  getSelectedTotalPoints,
  getVisibleRoundNumbers,
} from './standingsUtils';

describe('standingsUtils', () => {
  it('uses current total points when current round has no round breakdown', () => {
    expect(
      getSelectedTotalPoints(
        {
          team_name: 'Alpha',
          total_points: 12,
          round_points: null,
        },
        2,
        2
      )
    ).toBe(12);
  });

  it('rebuilds cumulative totals through the selected round', () => {
    expect(
      getSelectedTotalPoints(
        {
          team_name: 'Alpha',
          total_points: 27,
          round_points: { '1': 5, '2': 2, '3': 20 },
        },
        2,
        3
      )
    ).toBe(7);
  });

  it('sorts standings by cumulative points through the selected round', () => {
    const members = buildStandingsMembers(
      [
        {
          id: 'member-a',
          team_name: 'Alpha',
          total_points: 27,
          round_points: { '1': 5, '2': 2, '3': 20 },
        },
        {
          id: 'member-b',
          team_name: 'Bravo',
          total_points: 15,
          round_points: { '1': 4, '2': 6, '3': 5 },
        },
      ],
      2,
      3
    );

    expect(members.map((member) => member.team_name)).toEqual([
      'Bravo',
      'Alpha',
    ]);
    expect(members.map((member) => member.selected_total_points)).toEqual([
      10, 7,
    ]);
  });

  it('filters visible round columns to the selected round', () => {
    expect(getVisibleRoundNumbers([1, 2, 3, 4], 2)).toEqual([1, 2]);
  });
});
