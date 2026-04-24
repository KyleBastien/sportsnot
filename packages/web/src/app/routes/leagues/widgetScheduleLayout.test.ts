import { describe, expect, it } from '@rstest/core';
import type { WidgetSnapshot } from '@sportsnot/widget-api';
import {
  buildWidgetGameCards,
  formatWidgetGameHeader,
  formatWidgetTeamLines,
} from './widgetScheduleLayout';

function makeSnapshot(): WidgetSnapshot {
  return {
    league: {
      id: 'league-1',
      name: 'Playoff League',
      shareCode: 'SHARE',
      currentRound: 2,
      status: 'active',
    },
    date: '2026-04-23',
    generatedAt: '2026-04-23T12:00:00Z',
    games: [
      {
        id: 20,
        startsAt: '2026-04-24T02:00:00Z',
        state: 'LIVE',
        homeTeamId: 52,
        homeTeamAbbrev: 'WPG',
        homeTeamName: 'Jets',
        homeScore: 3,
        awayTeamId: 25,
        awayTeamAbbrev: 'DAL',
        awayTeamName: 'Stars',
        awayScore: 2,
        period: 2,
        timeRemaining: '11:02',
        hasDraftedPlayers: true,
      },
      {
        id: 10,
        startsAt: '2026-04-23T23:00:00Z',
        state: 'OFF',
        homeTeamId: 12,
        homeTeamAbbrev: 'CAR',
        homeTeamName: 'Hurricanes',
        homeScore: 4,
        awayTeamId: 13,
        awayTeamAbbrev: 'FLA',
        awayTeamName: 'Panthers',
        awayScore: 1,
        period: 3,
        timeRemaining: null,
        hasDraftedPlayers: false,
      },
    ],
    players: [
      {
        playerId: 1,
        teamId: null,
        name: 'Roope Hintz',
        teamAbbrev: 'DAL',
        position: 'F',
        gameId: 20,
        fantasyPoints: 4,
        dailyFantasyPoints: 1,
        ownedByTeamName: 'Alpha',
      },
      {
        playerId: 2,
        teamId: null,
        name: 'Jason Robertson',
        teamAbbrev: 'DAL',
        position: 'F',
        gameId: 20,
        fantasyPoints: 1,
        dailyFantasyPoints: 0,
        ownedByTeamName: 'Alpha',
      },
      {
        playerId: 3,
        teamId: null,
        name: 'Connor Hellebuyck',
        teamAbbrev: 'WPG',
        position: 'G',
        gameId: 20,
        fantasyPoints: 3,
        dailyFantasyPoints: 2,
        ownedByTeamName: 'Bravo',
      },
    ],
  };
}

describe('widgetScheduleLayout', () => {
  it('buildWidgetGameCards sorts games chronologically', () => {
    const cards = buildWidgetGameCards(makeSnapshot());

    expect(cards.map((card) => card.game.id)).toEqual([10, 20]);
  });

  it('buildWidgetGameCards groups fantasy teams by total points', () => {
    const cards = buildWidgetGameCards(makeSnapshot());

    expect(cards[1].fantasyTeams.map((team) => team.name)).toEqual([
      'Alpha',
      'Bravo',
    ]);
    expect(formatWidgetTeamLines(cards[1].fantasyTeams[0])).toEqual([
      '- DAL: Roope Hintz 4 +1, Jason Robertson 1 +0',
    ]);
  });

  it('formatWidgetGameHeader matches live and final widget text', () => {
    const [finalGame, liveGame] = makeSnapshot().games.sort(
      (lhs, rhs) => lhs.id - rhs.id
    );

    expect(formatWidgetGameHeader(finalGame)).toBe('FLA @ CAR - 1-4 F');
    expect(formatWidgetGameHeader(liveGame)).toBe('DAL @ WPG - 2-3 P2 11:02');
  });
});
