import { describe, expect, it } from '@rstest/core';
import {
  buildDailyFantasyPointMaps,
  isFinalWidgetGameState,
  type WidgetDailyFantasyBoxscore,
  type WidgetDailyFantasyGame,
} from './widget-daily-fantasy';

describe('widget daily fantasy helpers', () => {
  it('builds live skater deltas from same-day boxscores', () => {
    const games: WidgetDailyFantasyGame[] = [
      {
        id: 1,
        state: 'LIVE',
        homeTeam: { id: 100, score: 2 },
        awayTeam: { id: 200, score: 1 },
      },
    ];
    const boxscoresByGameId = new Map<number, WidgetDailyFantasyBoxscore>([
      [
        1,
        {
          playerByGameStats: {
            homeTeam: {
              forwards: [{ playerId: 11, goals: 1, assists: 1 }],
              defense: [{ playerId: 12, goals: 0, assists: 2 }],
            },
            awayTeam: {
              forwards: [{ playerId: 21, goals: 1, assists: 0 }],
            },
          },
        },
      ],
    ]);

    const { playerDailyPointsById, teamDailyPointsById } =
      buildDailyFantasyPointMaps(games, boxscoresByGameId);

    expect(playerDailyPointsById.get(11)).toBe(2);
    expect(playerDailyPointsById.get(12)).toBe(2);
    expect(playerDailyPointsById.get(21)).toBe(1);
    expect(teamDailyPointsById.get(100)).toBe(0);
    expect(teamDailyPointsById.get(200)).toBe(0);
  });

  it('only awards goalie or team delta once game is final', () => {
    const games: WidgetDailyFantasyGame[] = [
      {
        id: 1,
        state: 'LIVE',
        homeTeam: { id: 100, score: 3 },
        awayTeam: { id: 200, score: 0 },
      },
      {
        id: 2,
        state: 'FINAL',
        homeTeam: { id: 300, score: 4 },
        awayTeam: { id: 400, score: 0 },
      },
      {
        id: 3,
        state: 'OFF',
        homeTeam: { id: 500, score: 3 },
        awayTeam: { id: 600, score: 1 },
      },
    ];

    const { teamDailyPointsById } = buildDailyFantasyPointMaps(
      games,
      new Map()
    );

    expect(teamDailyPointsById.get(100)).toBe(0);
    expect(teamDailyPointsById.get(200)).toBe(0);
    expect(teamDailyPointsById.get(300)).toBe(4);
    expect(teamDailyPointsById.get(400)).toBe(0);
    expect(teamDailyPointsById.get(500)).toBe(2);
    expect(teamDailyPointsById.get(600)).toBe(0);
  });

  it('treats FINAL and OFF as finalized states', () => {
    expect(isFinalWidgetGameState('FINAL')).toBe(true);
    expect(isFinalWidgetGameState('OFF')).toBe(true);
    expect(isFinalWidgetGameState('LIVE')).toBe(false);
    expect(isFinalWidgetGameState('PRE')).toBe(false);
  });
});
